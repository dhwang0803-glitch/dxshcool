"""Phase 3: CF + Vector 후보 리랭킹 → hybrid_recommendation 적재.

serving.vod_recommendation 후보 × vod_tag × user_preference
→ hybrid_score 계산 → 상위 10건 + explanation_tags 생성
→ serving.hybrid_recommendation UPSERT

시리즈 중복제거는 CF_Engine/Vector_Search 단계에서 이미 처리됨.
reranker는 그 결과를 그대로 받아 hybrid_score 기준 재정렬만 수행.

성능 최적화 (전체 dump 구조):
  이전: 1,000유저 청크 루프 × (fetch_candidates + fetch_prefs + fetch_vod_tags + INSERT)
        → 243청크 × 4회 = ~972 DB 왕복
  현재: 루프 밖에서 전체 데이터 3번 dump → 순수 Python 계산 → 배치 INSERT
        → 읽기 3회 + INSERT ~수십 회 (총 DB 왕복 대폭 감소)
"""

import json
import logging
from statistics import mean

from Hybrid_Layer.src.base import HybridBase

log = logging.getLogger(__name__)


class Reranker(HybridBase):
    """Phase 3: CF + Vector 후보 리랭킹."""

    # ── 단일 유저용 (테스트/디버깅 용도) ────────────────────────────

    @staticmethod
    def _fetch_user_candidates(cur, user_id: str, test_mode: bool = False) -> list[dict]:
        """유저의 vod_recommendation 후보 조회.

        VS 후보는 source_vod_id 기반 중복제거 (source당 최고 점수 1건).
        """
        table = "serving.vod_recommendation_test" if test_mode else "serving.vod_recommendation"
        cur.execute(
            f"""
            SELECT vod_id_fk, score, recommendation_type, source_vod_id
            FROM {table}
            WHERE user_id_fk = %s
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY score DESC
            """,
            (user_id,),
        )
        candidates = []
        seen_vs_source: set[str] = set()
        for vid, score, rec_type, source_vod_id in cur.fetchall():
            if rec_type == "VISUAL_SIMILARITY" and source_vod_id:
                if source_vod_id in seen_vs_source:
                    continue
                seen_vs_source.add(source_vod_id)
            candidates.append({
                "vod_id_fk": vid,
                "score": score,
                "recommendation_type": rec_type,
            })
        return candidates

    @staticmethod
    def _fetch_user_preferences(cur, user_id: str) -> dict[tuple[str, str], float]:
        """유저 선호 태그 조회 → {(category, value): affinity}."""
        cur.execute(
            """
            SELECT tag_category, tag_value, affinity
            FROM public.user_preference
            WHERE user_id_fk = %s
            ORDER BY affinity DESC
            """,
            (user_id,),
        )
        return {(r[0], r[1]): r[2] for r in cur.fetchall()}

    @staticmethod
    def _fetch_vod_tags(cur, vod_ids: list[str]) -> dict[str, list[tuple[str, str, float]]]:
        """VOD ID 목록의 태그 조회 → {vod_id: [(category, value, confidence), ...]}."""
        if not vod_ids:
            return {}
        cur.execute(
            """
            SELECT vod_id_fk, tag_category, tag_value, confidence
            FROM public.vod_tag
            WHERE vod_id_fk = ANY(%s)
            """,
            (vod_ids,),
        )
        result: dict[str, list] = {}
        for r in cur.fetchall():
            result.setdefault(r[0], []).append((r[1], r[2], r[3]))
        return result

    # ── 전체 dump (run 전용) ────────────────────────────────────

    @staticmethod
    def _dump_all_candidates(cur, src_table: str) -> dict[str, list[dict]]:
        """CF+VS 후보 전체를 한 번에 로드 → {user_id: [candidate, ...]}.

        VS(VISUAL_SIMILARITY) 후보는 source_vod_id 기반 중복제거를 적용한다.
        동일 source VOD에서 파생된 추천이 여러 개면 최고 점수 1건만 유지.
        CF(COLLABORATIVE) 후보는 기존대로 vod_id 중복제거만 적용.
        """
        cur.execute(
            f"""
            SELECT user_id_fk, vod_id_fk, score, recommendation_type,
                   source_vod_id
            FROM {src_table}
            WHERE user_id_fk IS NOT NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            ORDER BY user_id_fk, score DESC
            """
        )
        result: dict[str, list] = {}
        seen_vods: dict[str, set] = {}        # vod_id 중복 (전 타입)
        seen_vs_source: dict[str, set] = {}   # VS source_vod_id 중복
        for user_id, vod_id, score, rec_type, source_vod_id in cur.fetchall():
            if user_id not in seen_vods:
                seen_vods[user_id] = set()
                seen_vs_source[user_id] = set()
                result[user_id] = []
            if vod_id in seen_vods[user_id]:
                continue
            # VS 후보: source_vod_id당 1건만
            if rec_type == "VISUAL_SIMILARITY" and source_vod_id:
                if source_vod_id in seen_vs_source[user_id]:
                    continue
                seen_vs_source[user_id].add(source_vod_id)
            seen_vods[user_id].add(vod_id)
            result[user_id].append({
                "vod_id_fk": vod_id,
                "score": score,
                "recommendation_type": rec_type,
            })
        return result

    @staticmethod
    def _dump_all_preferences(cur) -> dict[str, dict[tuple[str, str], float]]:
        """user_preference 전체를 한 번에 로드 → {user_id: {(cat, val): affinity}}."""
        cur.execute(
            """
            SELECT user_id_fk, tag_category, tag_value, affinity
            FROM public.user_preference
            """
        )
        result: dict[str, dict] = {}
        for user_id, cat, val, aff in cur.fetchall():
            result.setdefault(user_id, {})[(cat, val)] = aff
        return result

    # ── VS 시리즈 확장 ────────────────────────────────────────────

    @staticmethod
    def _load_series_map(cur) -> dict[str, list[str]]:
        """시리즈 대표 VOD → 에피소드 목록 매핑 로드.

        Returns: {representative_vod_id: [ep_vod_id, ...]}
        """
        cur.execute("""
            SELECT se.representative_vod_id, v.full_asset_id
            FROM public.vod_series_embedding se
            JOIN public.vod v ON v.series_nm = se.series_nm
            WHERE v.full_asset_id != se.representative_vod_id
        """)
        mapping: dict[str, list[str]] = {}
        for rep_id, ep_id in cur.fetchall():
            mapping.setdefault(rep_id, []).append(ep_id)
        return mapping

    @staticmethod
    def _expand_vs_candidates(
        all_candidates: dict[str, list[dict]],
        series_map: dict[str, list[str]],
    ) -> int:
        """VS 후보의 시리즈 대표 VOD를 에피소드로 확장 (in-place).

        대표 VOD 1건 → 같은 시리즈 에피소드 N건으로 확장.
        이미 다른 후보로 존재하는 에피소드는 스킵 (중복 방지).

        Returns: 총 확장된 에피소드 수
        """
        expanded_total = 0
        for user_id, cands in all_candidates.items():
            seen_vods = {c["vod_id_fk"] for c in cands}
            new_cands = []
            for c in cands:
                if c["recommendation_type"] != "VISUAL_SIMILARITY":
                    continue
                episodes = series_map.get(c["vod_id_fk"], [])
                for ep_id in episodes:
                    if ep_id not in seen_vods:
                        seen_vods.add(ep_id)
                        new_cands.append({
                            "vod_id_fk": ep_id,
                            "score": c["score"],
                            "recommendation_type": "VISUAL_SIMILARITY",
                        })
                        expanded_total += 1
            cands.extend(new_cands)
        return expanded_total

    # ── 순수 스코어링 (DB 호출 없음) ────────────────────────────────

    @staticmethod
    def score_user(
        candidates: list[dict],
        user_prefs: dict[tuple[str, str], float],
        vod_tags: dict[str, list[tuple[str, str, float]]],
        beta: float,
        top_n: int,
        top_k_tags: int,
        cf_slots: int = 0,
    ) -> list[dict]:
        """사전 조회된 데이터로 단일 유저 hybrid_score 계산 → 상위 top_n 반환.

        DB 호출 없음 — run의 bulk 구조 내부에서 사용.

        Args:
            cf_slots: CF 우선 슬롯 수. 0이면 전체 hybrid_score 경쟁.
                      > 0이면 CF 상위 cf_slots개를 먼저 확보,
                      나머지 (top_n - cf_slots)은 전체 후보에서 채움.
        """
        if not candidates:
            return []

        if not user_prefs:
            return [
                {
                    "vod_id_fk": c["vod_id_fk"],
                    "rank": i,
                    "score": c["score"],
                    "explanation_tags": [],
                    "source_engines": [c["recommendation_type"]],
                }
                for i, c in enumerate(candidates[:top_n], 1)
            ]

        scored = []
        for c in candidates:
            vid = c["vod_id_fk"]
            tags = vod_tags.get(vid, [])

            matched = []
            for cat, val, _conf in tags:
                aff = user_prefs.get((cat, val))
                if aff is not None:
                    matched.append({"category": cat, "value": val, "affinity": aff})

            matched.sort(key=lambda x: x["affinity"], reverse=True)

            top_affinities = [m["affinity"] for m in matched[:top_k_tags]]
            tag_overlap_score = mean(top_affinities) if top_affinities else 0.0

            hybrid_score = beta * c["score"] + (1 - beta) * tag_overlap_score

            scored.append({
                "vod_id_fk": vid,
                "hybrid_score": min(hybrid_score, 1.0),
                "explanation_tags": matched[:5],
                "source_engines": [c["recommendation_type"]],
            })

        scored.sort(key=lambda x: x["hybrid_score"], reverse=True)

        # ── CF 우선 슬롯 블렌딩 ──────────────────────────────
        if cf_slots > 0 and cf_slots < top_n:
            cf_items = [s for s in scored if "COLLABORATIVE" in s["source_engines"]]
            selected_vods = set()
            final = []

            # 1) CF 상위 cf_slots개 확보
            for s in cf_items[:cf_slots]:
                final.append(s)
                selected_vods.add(s["vod_id_fk"])

            # 2) 나머지 슬롯은 전체 후보에서 점수순 (이미 선택된 건 제외)
            remaining = top_n - len(final)
            for s in scored:
                if remaining <= 0:
                    break
                if s["vod_id_fk"] not in selected_vods:
                    final.append(s)
                    selected_vods.add(s["vod_id_fk"])
                    remaining -= 1

            scored = final

        return [
            {
                "vod_id_fk": s["vod_id_fk"],
                "rank": i,
                "score": round(s["hybrid_score"], 6),
                "explanation_tags": s["explanation_tags"],
                "source_engines": s["source_engines"],
            }
            for i, s in enumerate(scored[:top_n], 1)
        ]

    def rerank_user(
        self,
        cur,
        user_id: str,
        beta: float = 0.6,
        top_n: int = 10,
        top_k_tags: int = 3,
        test_mode: bool = False,
    ) -> list[dict]:
        """단일 유저 리랭킹 (테스트/디버깅 용도).

        운영 배치에서는 run의 bulk 구조를 사용한다.
        """
        candidates = self._fetch_user_candidates(cur, user_id, test_mode=test_mode)
        user_prefs = self._fetch_user_preferences(cur, user_id)
        vod_ids = [c["vod_id_fk"] for c in candidates]
        vod_tags = self._fetch_vod_tags(cur, vod_ids)
        return self.score_user(candidates, user_prefs, vod_tags, beta, top_n, top_k_tags)

    # ── 전체 파이프라인 ─────────────────────────────────────────────

    @staticmethod
    def _normalize_scores_by_type(all_candidates: dict[str, list[dict]]) -> None:
        """recommendation_type별 min-max 정규화 (in-place).

        CF(COLLABORATIVE)와 VISUAL_SIMILARITY의 score 스케일이 다를 때
        동일 [0, 1] 범위로 정규화하여 리랭킹 시 한쪽이 과대 표현되는 것을 방지.
        """
        # 타입별 min/max 수집
        type_stats: dict[str, dict] = {}
        for cands in all_candidates.values():
            for c in cands:
                rt = c["recommendation_type"]
                s = c["score"]
                if rt not in type_stats:
                    type_stats[rt] = {"min": s, "max": s}
                else:
                    if s < type_stats[rt]["min"]:
                        type_stats[rt]["min"] = s
                    if s > type_stats[rt]["max"]:
                        type_stats[rt]["max"] = s

        # 타입이 1개뿐이면 정규화 불필요
        if len(type_stats) <= 1:
            return

        log.info("스코어 정규화: %s",
                 {rt: f"[{st['min']:.4f}, {st['max']:.4f}]" for rt, st in type_stats.items()})

        # in-place 정규화
        for cands in all_candidates.values():
            for c in cands:
                st = type_stats[c["recommendation_type"]]
                span = st["max"] - st["min"]
                if span > 0:
                    c["score"] = (c["score"] - st["min"]) / span
                else:
                    c["score"] = 0.5

    def run(
        self,
        conn,
        beta: float = 0.6,
        top_n: int = 10,
        top_k_tags: int = 3,
        user_chunk_size: int = 1000,
        test_mode: bool = False,
        normalize_scores: bool = False,
        expand_vs: bool = False,
        cf_slots: int = 0,
    ) -> int:
        """전체 유저 리랭킹 → hybrid_recommendation 적재.

        Args:
            user_chunk_size: INSERT 배치 크기 (유저 수 기준). rows = user_chunk_size × top_n.
            test_mode: True이면 vod_recommendation_test에서 후보 조회,
                       hybrid_recommendation_test에 결과 적재 (테스터 격리용).
            normalize_scores: True이면 recommendation_type별 min-max 정규화 적용.
            expand_vs: True이면 VS 시리즈 대표 VOD를 에피소드로 확장.
            cf_slots: CF 우선 슬롯 수. 0이면 비활성 (전체 hybrid_score 경쟁).
                      예: cf_slots=7이면 top_n=10 중 CF 상위 7 + 나머지 3은 전체 경쟁.

        Returns:
            총 적재 레코드 수
        """
        src_table = "serving.vod_recommendation_test" if test_mode else "serving.vod_recommendation"
        dst_table = "serving.hybrid_recommendation_test" if test_mode else "serving.hybrid_recommendation"
        mode_label = "TEST 유저" if test_mode else "실 유저"
        log.info("Phase 3: Hybrid reranking (%s, beta=%.2f, top_n=%d)", mode_label, beta, top_n)

        # ── Step 1: 전체 데이터 로드 ─────────────────────────────
        with conn.cursor() as cur:
            log.info("[1/4] 후보 전체 dump...")
            all_candidates = self._dump_all_candidates(cur, src_table)
            user_ids = list(all_candidates.keys())
            log.info("  -> %d users, 후보 로드 완료", len(user_ids))

            if not user_ids:
                return 0

            # ── Step 1.5: VS 시리즈 확장 (옵션) ──────────────────
            if expand_vs:
                log.info("[1.5] VS 시리즈 확장: 시리즈 맵 로드...")
                series_map = self._load_series_map(cur)
                log.info("  -> %d 시리즈 대표 VOD 맵 로드", len(series_map))
                n_expanded = self._expand_vs_candidates(all_candidates, series_map)
                log.info("  -> %d 에피소드 확장 완료", n_expanded)

            log.info("[2/4] user_preference 전체 dump...")
            all_prefs = self._dump_all_preferences(cur)
            log.info("  -> %d users 선호 태그 로드 완료", len(all_prefs))

            unique_vod_ids = list({
                c["vod_id_fk"]
                for cands in all_candidates.values()
                for c in cands
            })
            log.info("[3/4] vod_tag dump (%d개 고유 VOD)...", len(unique_vod_ids))
            all_vod_tags = self._fetch_vod_tags(cur, unique_vod_ids)
            log.info("  -> %d VOD 태그 로드 완료", len(all_vod_tags))

        # ── Step 1.6: 스코어 정규화 (옵션) ────────────────────
        if normalize_scores:
            self._normalize_scores_by_type(all_candidates)

        # ── Step 2: 기존 데이터 삭제 ─────────────────────────────
        with conn.cursor() as cur:
            cur.execute(f"DELETE FROM {dst_table}")
            log.info("Cleared %d existing %s rows", cur.rowcount, dst_table)
        conn.commit()

        # ── Step 3: 순수 Python 스코어링 (DB 왕복 없음) ──────────
        log.info("Python 스코어링 시작 (%d users)...", len(user_ids))
        all_rows = []
        for uid in user_ids:
            candidates = all_candidates[uid]
            user_prefs = all_prefs.get(uid, {})
            recs = self.score_user(candidates, user_prefs, all_vod_tags, beta, top_n, top_k_tags, cf_slots)
            for r in recs:
                all_rows.append((
                    uid,
                    r["vod_id_fk"],
                    r["rank"],
                    r["score"],
                    json.dumps(r["explanation_tags"], ensure_ascii=False),
                    r["source_engines"],
                ))
        log.info("스코어링 완료: %d rows", len(all_rows))

        # ── Step 4: 배치 INSERT (커넥션 재생성) ─────────────────
        conn.close()
        conn = self.get_conn()
        log.info("DB 커넥션 재생성 완료 (INSERT용)")

        insert_batch = user_chunk_size * top_n
        total_inserted = self.batch_upsert(
            conn,
            sql_template=f"""
                INSERT INTO {dst_table}
                    (user_id_fk, vod_id_fk, rank, score, explanation_tags, source_engines)
                VALUES {{args}}
                ON CONFLICT (user_id_fk, vod_id_fk) DO UPDATE SET
                    rank = EXCLUDED.rank,
                    score = EXCLUDED.score,
                    explanation_tags = EXCLUDED.explanation_tags,
                    source_engines = EXCLUDED.source_engines,
                    generated_at = NOW(),
                    expires_at = NOW() + INTERVAL '7 days'
            """,
            rows=all_rows,
            format_str="(%s,%s,%s,%s,%s::jsonb,%s)",
            batch_size=insert_batch,
            commit_per_batch=True,
        )

        log.info("Phase 3 완료: %d hybrid_recommendation rows", total_inserted)
        return total_inserted


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
reranker = Reranker()
rerank_user = reranker.rerank_user
run_hybrid_reranking = reranker.run
