"""Phase 4: 선호 태그별 VOD 추천 선반 생성.

user_preference → 카테고리별 top N 태그
→ 태그별 vod_tag 매칭 + 시청 제외 + 랭킹
→ 태그별 top 10 VOD 선별 (10개 미달 태그는 스킵 → 후순위 대체)
→ serving.tag_recommendation 적재

카테고리별 슬롯:
  홈:       genre 3
  스마트:   genre_detail 3, director 2, actor_lead 2, actor_guest 2

최적화 전략 (전체 dump 구조):
  이전: 1,000유저 청크 루프 × (user_pref + vod_tag + watch_history + cold_start + INSERT)
        → 243청크 × 5~6회 = ~1,200~1,500 DB 왕복, 인기 태그 243번 재조회
  현재: 전체 데이터 4번 dump → 순수 Python 계산 → 배치 INSERT
        → 읽기 4회 + INSERT 수십 회 (DB 왕복 대폭 감소)
"""

import logging

from Hybrid_Layer.src.base import HybridBase

log = logging.getLogger(__name__)

# 태그당 VOD 후보 버퍼 (시청 제외 + 시리즈 중복제거 후 vods_per_tag개를 보장하기 위한 여유분)
_TAG_VOD_BUFFER = 500

# 카테고리별 최종 슬롯 수 (홈: genre, 스마트: 나머지)
_CATEGORY_SLOTS = {
    "genre": 3,
    "genre_detail": 3,
    "director": 2,
    "actor_lead": 2,
    "actor_guest": 2,
}
# 10개 미달 스킵 대비 여유 후보 태그 수 (슬롯 + 버퍼)
_CATEGORY_BUFFER = 3


class ShelfBuilder(HybridBase):
    """Phase 4: 선호 태그별 VOD 추천 선반 생성."""

    def _dump_user_preferences(self, conn, test_mode: bool, allowed_cats: list, max_cat_slots: int):
        """user_preference 전체 dump → user별 카테고리별 태그 목록."""
        is_test_filter = self.is_test_filter("u", test_mode)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT up.user_id_fk, up.tag_category, up.tag_value, up.affinity,
                       ROW_NUMBER() OVER (
                           PARTITION BY up.user_id_fk, up.tag_category
                           ORDER BY up.affinity DESC
                       ) AS cat_rank
                FROM public.user_preference up
                JOIN public."user" u ON u.sha2_hash = up.user_id_fk
                WHERE up.tag_category = ANY(%s)
                  {is_test_filter}
                """,
                (allowed_cats,),
            )
            user_tags_by_cat: dict[str, dict[str, list]] = {}
            unique_tags: set[tuple] = set()
            for user_id, cat, val, aff, cat_rank in cur.fetchall():
                if cat_rank > max_cat_slots:
                    continue
                user_tags_by_cat.setdefault(user_id, {}).setdefault(cat, []).append(
                    (cat_rank, val, aff)
                )
                unique_tags.add((cat, val))
        return user_tags_by_cat, unique_tags

    @staticmethod
    def _build_tag_vod_cache(conn, tag_list: list[tuple]) -> dict[tuple, list]:
        """태그별 VOD 후보 캐시 빌드."""
        if not tag_list:
            return {}
        tag_cats = [t[0] for t in tag_list]
        tag_vals = [t[1] for t in tag_list]
        tag_vod_cache: dict[tuple, list] = {}
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.tag_category, t.tag_value, t.vod_id_fk,
                       v.ct_cl, v.series_nm
                FROM (
                    SELECT vt.tag_category, vt.tag_value, vt.vod_id_fk,
                           ROW_NUMBER() OVER (
                               PARTITION BY vt.tag_category, vt.tag_value
                               ORDER BY vt.confidence DESC
                           ) AS rn
                    FROM public.vod_tag vt
                    JOIN (
                        SELECT unnest(%s::varchar[]) AS tag_category,
                               unnest(%s::varchar[]) AS tag_value
                    ) ct ON ct.tag_category = vt.tag_category
                         AND ct.tag_value = vt.tag_value
                ) t
                JOIN public.vod v ON v.full_asset_id = t.vod_id_fk
                WHERE t.rn <= %s
                  AND v.poster_url IS NOT NULL
                """,
                (tag_cats, tag_vals, _TAG_VOD_BUFFER),
            )
            for cat, val, vod_id, ct_cl, series_nm in cur.fetchall():
                tag_vod_cache.setdefault((cat, val), []).append(
                    (vod_id, ct_cl or "", series_nm or vod_id)
                )
        return tag_vod_cache

    def _dump_watch_history(self, conn, test_mode: bool) -> dict[str, set]:
        """watch_history 전체 dump → {user_id: {watched vod_ids}}."""
        is_test_filter = self.is_test_filter("u", test_mode)
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT wh.user_id_fk, wh.vod_id_fk
                FROM public.watch_history wh
                JOIN public."user" u ON u.sha2_hash = wh.user_id_fk
                WHERE TRUE {is_test_filter}
                """
            )
            watched: dict[str, set] = {}
            for user_id, vod_id in cur.fetchall():
                watched.setdefault(user_id, set()).add(vod_id)
        return watched

    def _prepare_cold_start(self, conn, user_ids: list, test_mode: bool,
                            tag_vod_cache: dict) -> tuple[dict, dict]:
        """Cold start 사전 준비: 연령대별 인기 genre_detail 태그."""
        is_test_filter = self.is_test_filter("u", test_mode)
        max_cold_tags = max(_CATEGORY_SLOTS.values()) + _CATEGORY_BUFFER + 5

        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT u.sha2_hash, u.age_grp10
                FROM public."user" u
                WHERE u.sha2_hash = ANY(%s)
                  {is_test_filter}
                """,
                (user_ids,),
            )
            user_ages: dict[str, str] = {r[0]: r[1] for r in cur.fetchall()}

        age_groups = set(user_ages.values())
        age_cold_tags: dict[str, list[str]] = {}
        cold_unique_tags: set[tuple] = set()

        with conn.cursor() as cur:
            for age in age_groups:
                cur.execute(
                    """
                    SELECT vt.tag_value, COUNT(DISTINCT wh.user_id_fk) AS user_cnt
                    FROM public.watch_history wh
                    JOIN public."user" u ON u.sha2_hash = wh.user_id_fk
                    JOIN public.vod_tag vt ON vt.vod_id_fk = wh.vod_id_fk
                    WHERE u.age_grp10 = %s
                      AND u.is_test = FALSE
                      AND vt.tag_category = 'genre_detail'
                    GROUP BY vt.tag_value
                    HAVING COUNT(DISTINCT wh.user_id_fk) >= 3
                    ORDER BY user_cnt DESC
                    LIMIT %s
                    """,
                    (age, max_cold_tags),
                )
                tags = [r[0] for r in cur.fetchall()]
                age_cold_tags[age] = tags
                for val in tags:
                    key = ("genre_detail", val)
                    if key not in tag_vod_cache:
                        cold_unique_tags.add(key)

        # cold 전용 태그 VOD도 캐시에 추가
        if cold_unique_tags:
            cold_cache = self._build_tag_vod_cache(conn, list(cold_unique_tags))
            for key, vods in cold_cache.items():
                tag_vod_cache.setdefault(key, []).extend(vods)
            log.info("  → cold 전용 태그 %d개 추가", len(cold_unique_tags))

        return user_ages, age_cold_tags

    @staticmethod
    def _assemble_shelves(user_ids, user_tags_by_cat, tag_vod_cache, watched,
                          user_ages, age_cold_tags, vods_per_tag) -> list[tuple]:
        """순수 Python 선반 조립 — DB 호출 없음."""
        total_slots = sum(_CATEGORY_SLOTS.values())
        _MAX_COLD_RANK = 5
        all_rows = []

        for user_id in user_ids:
            cats_dict = user_tags_by_cat[user_id]
            user_watched = watched.get(user_id, set())
            filled = 0
            user_assigned_tags: set[tuple] = set()

            for cat, slots in _CATEGORY_SLOTS.items():
                candidates = cats_dict.get(cat, [])
                candidates.sort(key=lambda x: x[0])
                assigned_rank = 0

                for _cat_rank, val, aff in candidates:
                    if assigned_rank >= slots:
                        break
                    candidate_vods = tag_vod_cache.get((cat, val), [])
                    tag_vods = []
                    seen_series: set = set()
                    for vod_id, ct_cl, series_nm in candidate_vods:
                        if vod_id in user_watched:
                            continue
                        is_episode_level = (cat == "actor_guest" and ct_cl == "TV 연예/오락")
                        if not is_episode_level:
                            if series_nm in seen_series:
                                continue
                            seen_series.add(series_nm)
                        tag_vods.append(vod_id)
                        if len(tag_vods) >= vods_per_tag:
                            break

                    if len(tag_vods) < vods_per_tag:
                        continue

                    assigned_rank += 1
                    filled += 1
                    user_assigned_tags.add((cat, val))
                    vod_score = min(round(aff, 6), 1.0)
                    for vod_idx, vod_id in enumerate(tag_vods, 1):
                        all_rows.append((
                            user_id, cat, val, assigned_rank, round(aff, 6),
                            vod_id, vod_idx, vod_score,
                        ))

            # Cold start fallback
            unfilled = total_slots - filled
            if unfilled > 0:
                age = user_ages.get(user_id)
                if age:
                    cold_tags = age_cold_tags.get(age, [])
                    cold_rank = 0
                    for tag_val in cold_tags:
                        if cold_rank >= min(unfilled, _MAX_COLD_RANK):
                            break
                        if ("genre_detail", tag_val) in user_assigned_tags:
                            continue
                        candidate_vods = tag_vod_cache.get(("genre_detail", tag_val), [])
                        tag_vods = []
                        seen_series = set()
                        for vod_id, _ct_cl, series_nm in candidate_vods:
                            if vod_id in user_watched:
                                continue
                            if series_nm in seen_series:
                                continue
                            seen_series.add(series_nm)
                            tag_vods.append(vod_id)
                            if len(tag_vods) >= vods_per_tag:
                                break
                        if len(tag_vods) < vods_per_tag:
                            continue
                        cold_rank += 1
                        for vod_idx, vod_id in enumerate(tag_vods, 1):
                            all_rows.append((
                                user_id, "cold_genre_detail", tag_val, cold_rank, 0.0,
                                vod_id, vod_idx, 0.0,
                            ))

        return all_rows

    def build(
        self,
        conn,
        vods_per_tag: int = 10,
        user_chunk_size: int = 1000,
        test_mode: bool = False,
    ) -> int:
        """전체 유저의 태그 선반 생성 → tag_recommendation 적재.

        Returns:
            총 적재 레코드 수
        """
        dst_table = "serving.tag_recommendation_test" if test_mode else "serving.tag_recommendation"
        mode_label = "TEST 유저" if test_mode else "실 유저"
        log.info("Phase 4: Building tag shelves (%s, vods_per_tag=%d)", mode_label, vods_per_tag)

        allowed_cats = list(_CATEGORY_SLOTS.keys())
        max_cat_slots = max(_CATEGORY_SLOTS.values()) + _CATEGORY_BUFFER

        # ── Step 1: user_preference 전체 dump ────────────────────
        log.info("[1/4] user_preference 전체 dump...")
        user_tags_by_cat, unique_tags = self._dump_user_preferences(
            conn, test_mode, allowed_cats, max_cat_slots
        )
        user_ids = list(user_tags_by_cat.keys())
        log.info("  → %d users, %d unique tags 로드 완료", len(user_ids), len(unique_tags))

        if not user_ids:
            return 0

        # ── Step 2: tag_vod_cache 빌드 ───────────────────────────
        log.info("[2/4] tag_vod_cache 전체 빌드 (%d tags)...", len(unique_tags))
        tag_vod_cache = self._build_tag_vod_cache(conn, list(unique_tags))
        log.info("  → %d tags VOD 캐시 빌드 완료", len(tag_vod_cache))

        # ── Step 3: watch_history 전체 dump ──────────────────────
        log.info("[3/4] watch_history 전체 dump...")
        watched = self._dump_watch_history(conn, test_mode)
        log.info("  → %d users 시청 이력 로드 완료", len(watched))

        # ── Step 4: cold start 사전 준비 ─────────────────────────
        log.info("[4/4] Cold start 사전 준비...")
        user_ages, age_cold_tags = self._prepare_cold_start(
            conn, user_ids, test_mode, tag_vod_cache
        )
        log.info("  → cold start 준비 완료 (%d age_grp)", len(set(user_ages.values())))

        # ── Step 5: 기존 데이터 삭제 ─────────────────────────────
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {dst_table}")
            log.info("Cleared %d existing %s rows", cur.rowcount, dst_table)
        conn.commit()

        # ── Step 6: 순수 Python 선반 조립 ────────────────────────
        log.info("Python 선반 조립 시작 (%d users)...", len(user_ids))
        all_rows = self._assemble_shelves(
            user_ids, user_tags_by_cat, tag_vod_cache, watched,
            user_ages, age_cold_tags, vods_per_tag,
        )
        log.info("선반 조립 완료: %d rows", len(all_rows))

        # ── Step 7: 배치 INSERT ──────────────────────────────────
        insert_batch = user_chunk_size * vods_per_tag
        total_inserted = self.batch_upsert(
            conn,
            sql_template=f"""
                INSERT INTO {dst_table}
                    (user_id_fk, tag_category, tag_value, tag_rank, tag_affinity,
                     vod_id_fk, vod_rank, vod_score)
                VALUES {{args}}
                ON CONFLICT (user_id_fk, tag_category, tag_value, vod_id_fk) DO UPDATE SET
                    tag_rank     = EXCLUDED.tag_rank,
                    tag_affinity = EXCLUDED.tag_affinity,
                    vod_rank     = EXCLUDED.vod_rank,
                    vod_score    = EXCLUDED.vod_score,
                    generated_at = NOW(),
                    expires_at   = NOW() + INTERVAL '7 days'
            """,
            rows=all_rows,
            format_str="(%s,%s,%s,%s,%s,%s,%s,%s)",
            batch_size=insert_batch,
            commit_per_batch=True,
        )

        log.info("Phase 4 완료: %d tag_recommendation rows", total_inserted)
        return total_inserted


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
shelf_builder = ShelfBuilder()
build_tag_shelves = shelf_builder.build
