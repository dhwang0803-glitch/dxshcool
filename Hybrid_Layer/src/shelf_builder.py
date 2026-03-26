"""Phase 4: 선호 태그별 VOD 추천 선반 생성.

user_preference → 카테고리별 top N 태그
→ 태그별 vod_tag 매칭 + 시청 제외 + 랭킹
→ 태그별 top 10 VOD 선별 (10개 미달 태그는 스킵 → 후순위 대체)
→ serving.tag_recommendation 적재

카테고리별 슬롯:
  홈:       genre 3
  스마트:   genre_detail 3, director 2, actor_lead 2, actor_guest 2

최적화 전략:
- 청크 내 등장하는 고유 (tag_category, tag_value)별로 상위 VOD를 한 번만 조회해 캐시
- 유저 루프에서는 캐시 조회 + 시청 이력 제외만 수행 (DB 왕복 없음)
- 청크 유저의 시청 이력은 watch_history 인덱스 조회로 한 번에 로드
"""

import logging

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


def build_tag_shelves(
    conn,
    vods_per_tag: int = 10,
    user_chunk_size: int = 1000,
    test_mode: bool = False,
) -> int:
    """전체 유저의 태그 선반 생성 → tag_recommendation 적재.

    카테고리별 슬롯 수만큼 태그를 선별하되, vods_per_tag개 미만의 VOD만
    남는 태그는 스킵하고 같은 카테고리의 후순위 태그로 대체한다.

    Args:
        test_mode: True이면 is_test=TRUE 유저만 처리 → tag_recommendation_test 적재.

    Returns:
        총 적재 레코드 수
    """
    dst_table = "serving.tag_recommendation_test" if test_mode else "serving.tag_recommendation"
    is_test_filter = "AND u.is_test = TRUE" if test_mode else "AND u.is_test = FALSE"
    mode_label = "TEST 유저" if test_mode else "실 유저"
    log.info("Phase 4: Building tag shelves (%s, vods_per_tag=%d)", mode_label, vods_per_tag)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT up.user_id_fk
            FROM public.user_preference up
            JOIN public."user" u ON u.sha2_hash = up.user_id_fk
            WHERE TRUE {is_test_filter}
            """
        )
        user_ids = [r[0] for r in cur.fetchall()]

    log.info("Target users: %d", len(user_ids))
    if not user_ids:
        return 0

    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {dst_table}")
        log.info("Cleared %d existing %s rows", cur.rowcount, dst_table)

    total_inserted = 0
    for chunk_start in range(0, len(user_ids), user_chunk_size):
        chunk = user_ids[chunk_start: chunk_start + user_chunk_size]

        # 허용 카테고리 목록 (rating 제외)
        allowed_cats = list(_CATEGORY_SLOTS.keys())

        with conn.cursor() as cur:
            # 1) 청크 유저의 카테고리별 top N 태그 조회 (rating 제외)
            #    카테고리별로 슬롯+버퍼만큼 후보를 가져온다
            cur.execute(
                """
                SELECT user_id_fk, tag_category, tag_value, affinity, cat_rank
                FROM (
                    SELECT user_id_fk, tag_category, tag_value, affinity,
                           ROW_NUMBER() OVER (
                               PARTITION BY user_id_fk, tag_category
                               ORDER BY affinity DESC
                           ) AS cat_rank
                    FROM public.user_preference
                    WHERE user_id_fk = ANY(%s)
                      AND tag_category = ANY(%s)
                ) sub
                WHERE cat_rank <= %s
                """,
                (chunk, allowed_cats, max(_CATEGORY_SLOTS.values()) + _CATEGORY_BUFFER),
            )
            rows = cur.fetchall()

        # user → {cat: [(cat_rank, val, aff), ...]}  affinity 내림차순
        user_tags_by_cat: dict[str, dict[str, list]] = {}
        unique_tags: set[tuple] = set()
        for user_id, cat, val, aff, cat_rank in rows:
            user_tags_by_cat.setdefault(user_id, {}).setdefault(cat, []).append(
                (cat_rank, val, aff)
            )
            unique_tags.add((cat, val))

        if not unique_tags:
            processed = min(chunk_start + user_chunk_size, len(user_ids))
            log.info("Progress: %d/%d users", processed, len(user_ids))
            continue

        # 2) 청크 내 고유 태그별 상위 VOD를 한 번만 조회 (캐시)
        #    인기 태그(드라마 등) 수만 건 중 상위 _TAG_VOD_BUFFER개만 가져옴
        tag_vod_cache: dict[tuple, list[str]] = {}
        tag_list = list(unique_tags)
        tag_cats = [t[0] for t in tag_list]
        tag_vals = [t[1] for t in tag_list]

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
                """,
                (tag_cats, tag_vals, _TAG_VOD_BUFFER),
            )
            for cat, val, vod_id, ct_cl, series_nm in cur.fetchall():
                tag_vod_cache.setdefault((cat, val), []).append(
                    (vod_id, ct_cl or "", series_nm or vod_id)
                )

        # 3) 청크 유저의 시청 이력 한 번에 로드
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id_fk, vod_id_fk FROM public.watch_history WHERE user_id_fk = ANY(%s)",
                (chunk,),
            )
            watched: dict[str, set] = {}
            for user_id, vod_id in cur.fetchall():
                watched.setdefault(user_id, set()).add(vod_id)

        # 4) 유저별 선반 조립 (메모리 연산, DB 왕복 없음)
        #    카테고리별 슬롯 수만큼 태그 선별, 10개 미달 → 스킵 후 후순위 대체
        batch_rows = []
        for user_id, cats_dict in user_tags_by_cat.items():
            user_watched = watched.get(user_id, set())

            for cat, slots in _CATEGORY_SLOTS.items():
                candidates = cats_dict.get(cat, [])
                candidates.sort(key=lambda x: x[0])  # cat_rank 순 (affinity 내림차순)
                assigned_rank = 0

                for _cat_rank, val, aff in candidates:
                    if assigned_rank >= slots:
                        break
                    # 태그별 VOD 필터링
                    candidate_vods = tag_vod_cache.get((cat, val), [])
                    tag_vods = []
                    seen_series: set = set()
                    for vod_id, ct_cl, series_nm in candidate_vods:
                        if vod_id in user_watched:
                            continue
                        # 에피소드 단위 유지:
                        # actor_guest + TV 연예/오락 → 게스트 출연 에피소드 몰아보기
                        # director + TV 연예/오락 → 감독 게스트 출연 에피소드 몰아보기
                        # actor_lead는 시리즈 중복제거 (같은 예능 레귤러 10편 방지)
                        is_episode_level = (cat in ("actor_guest", "director") and ct_cl == "TV 연예/오락")
                        if not is_episode_level:
                            if series_nm in seen_series:
                                continue
                            seen_series.add(series_nm)
                        tag_vods.append(vod_id)
                        if len(tag_vods) >= vods_per_tag:
                            break

                    # 10개 미달 → 이 태그 스킵, 후순위 태그로 대체
                    if len(tag_vods) < vods_per_tag:
                        continue

                    assigned_rank += 1
                    vod_score = min(round(aff, 6), 1.0)
                    for vod_idx, vod_id in enumerate(tag_vods, 1):
                        batch_rows.append((
                            user_id, cat, val, assigned_rank, round(aff, 6),
                            vod_id, vod_idx, vod_score,
                        ))

        # 5) 배치 INSERT
        if batch_rows:
            with conn.cursor() as cur:
                args = ",".join(
                    cur.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", row).decode()
                    for row in batch_rows
                )
                cur.execute(
                    f"""
                    INSERT INTO {dst_table}
                        (user_id_fk, tag_category, tag_value, tag_rank, tag_affinity,
                         vod_id_fk, vod_rank, vod_score)
                    VALUES {args}
                    ON CONFLICT (user_id_fk, tag_category, tag_value, vod_id_fk) DO UPDATE SET
                        tag_rank     = EXCLUDED.tag_rank,
                        tag_affinity = EXCLUDED.tag_affinity,
                        vod_rank     = EXCLUDED.vod_rank,
                        vod_score    = EXCLUDED.vod_score,
                        generated_at = NOW(),
                        expires_at   = NOW() + INTERVAL '7 days'
                    """
                )
                total_inserted += cur.rowcount
        conn.commit()

        processed = min(chunk_start + user_chunk_size, len(user_ids))
        log.info("Progress: %d/%d users", processed, len(user_ids))

    log.info("Phase 4 완료: %d tag_recommendation rows", total_inserted)
    return total_inserted
