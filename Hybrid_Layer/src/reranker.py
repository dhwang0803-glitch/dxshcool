"""Phase 3: CF + Vector 후보 리랭킹 → hybrid_recommendation 적재.

serving.vod_recommendation 후보 × vod_tag × user_preference
→ hybrid_score 계산 → 상위 10건 + explanation_tags 생성
→ serving.hybrid_recommendation UPSERT

시리즈 중복제거는 CF_Engine/Vector_Search 단계에서 이미 처리됨.
reranker는 그 결과를 그대로 받아 hybrid_score 기준 재정렬만 수행.

성능 최적화 (batch 구조):
  이전: 유저 1명당 DB 쿼리 3번 → 1,000유저 청크 = 3,000 queries/chunk
  현재: 청크 전체를 3번의 bulk 쿼리로 처리 → 3 queries/chunk (~10~20배 향상)
"""

import json
import logging
from statistics import mean

log = logging.getLogger(__name__)


# ── 단일 유저용 (테스트/디버깅 용도) ────────────────────────────────────

def _fetch_user_candidates(cur, user_id: str, test_mode: bool = False) -> list[dict]:
    """유저의 vod_recommendation 후보 조회."""
    table = "serving.vod_recommendation_test" if test_mode else "serving.vod_recommendation"
    cur.execute(
        f"""
        SELECT vod_id_fk, score, recommendation_type
        FROM {table}
        WHERE user_id_fk = %s
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY score DESC
        """,
        (user_id,),
    )
    seen = set()
    candidates = []
    for row in cur.fetchall():
        vid = row[0]
        if vid not in seen:
            seen.add(vid)
            candidates.append({
                "vod_id_fk": vid,
                "score": row[1],
                "recommendation_type": row[2],
            })
    return candidates


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


# ── 청크 단위 bulk 조회 (run_hybrid_reranking 전용) ──────────────────────

def _fetch_candidates_bulk(cur, user_ids: list[str], test_mode: bool = False) -> dict[str, list[dict]]:
    """청크 내 전체 유저의 후보를 한 번에 조회 → {user_id: [candidate, ...]}."""
    table = "serving.vod_recommendation_test" if test_mode else "serving.vod_recommendation"
    cur.execute(
        f"""
        SELECT user_id_fk, vod_id_fk, score, recommendation_type
        FROM {table}
        WHERE user_id_fk = ANY(%s)
          AND (expires_at IS NULL OR expires_at > NOW())
        ORDER BY user_id_fk, score DESC
        """,
        (user_ids,),
    )
    result: dict[str, list] = {}
    seen: dict[str, set] = {}
    for user_id, vod_id, score, rec_type in cur.fetchall():
        if user_id not in seen:
            seen[user_id] = set()
            result[user_id] = []
        if vod_id not in seen[user_id]:
            seen[user_id].add(vod_id)
            result[user_id].append({
                "vod_id_fk": vod_id,
                "score": score,
                "recommendation_type": rec_type,
            })
    return result


def _fetch_preferences_bulk(cur, user_ids: list[str]) -> dict[str, dict[tuple[str, str], float]]:
    """청크 내 전체 유저의 선호 태그를 한 번에 조회 → {user_id: {(cat, val): affinity}}."""
    cur.execute(
        """
        SELECT user_id_fk, tag_category, tag_value, affinity
        FROM public.user_preference
        WHERE user_id_fk = ANY(%s)
        """,
        (user_ids,),
    )
    result: dict[str, dict] = {}
    for user_id, cat, val, aff in cur.fetchall():
        result.setdefault(user_id, {})[(cat, val)] = aff
    return result


# ── 순수 스코어링 (DB 호출 없음) ────────────────────────────────────────

def _score_user(
    candidates: list[dict],
    user_prefs: dict[tuple[str, str], float],
    vod_tags: dict[str, list[tuple[str, str, float]]],
    beta: float,
    top_n: int,
    top_k_tags: int,
) -> list[dict]:
    """사전 조회된 데이터로 단일 유저 hybrid_score 계산 → 상위 top_n 반환.

    DB 호출 없음 — run_hybrid_reranking의 bulk 구조 내부에서 사용.
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
    cur,
    user_id: str,
    beta: float = 0.6,
    top_n: int = 10,
    top_k_tags: int = 3,
    test_mode: bool = False,
) -> list[dict]:
    """단일 유저 리랭킹 (테스트/디버깅 용도).

    운영 배치에서는 run_hybrid_reranking의 bulk 구조를 사용한다.
    """
    candidates = _fetch_user_candidates(cur, user_id, test_mode=test_mode)
    user_prefs = _fetch_user_preferences(cur, user_id)
    vod_ids = [c["vod_id_fk"] for c in candidates]
    vod_tags = _fetch_vod_tags(cur, vod_ids)
    return _score_user(candidates, user_prefs, vod_tags, beta, top_n, top_k_tags)


# ── 전체 파이프라인 ──────────────────────────────────────────────────────

def run_hybrid_reranking(
    conn,
    beta: float = 0.6,
    top_n: int = 10,
    top_k_tags: int = 3,
    user_chunk_size: int = 1000,
    test_mode: bool = False,
) -> int:
    """전체 유저 리랭킹 → hybrid_recommendation 적재.

    Args:
        test_mode: True이면 vod_recommendation_test에서 후보 조회,
                   hybrid_recommendation_test에 결과 적재 (테스터 격리용).

    청크 단위 bulk 쿼리 구조:
      1. 청크 내 전체 후보 한 번에 조회 (_fetch_candidates_bulk)
      2. 청크 내 전체 선호 태그 한 번에 조회 (_fetch_preferences_bulk)
      3. 청크 내 고유 VOD 태그 한 번에 조회 (_fetch_vod_tags)
      → 1,000유저 청크 기준 3 queries/chunk (기존 3,000 queries/chunk 대비 ~10~20배 향상)

    Returns:
        총 적재 레코드 수
    """
    src_table = "serving.vod_recommendation_test" if test_mode else "serving.vod_recommendation"
    dst_table = "serving.hybrid_recommendation_test" if test_mode else "serving.hybrid_recommendation"
    mode_label = "TEST 유저" if test_mode else "실 유저"
    log.info("Phase 3: Hybrid reranking (%s, beta=%.2f, top_n=%d)", mode_label, beta, top_n)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT user_id_fk
            FROM {src_table}
            WHERE user_id_fk IS NOT NULL
              AND (expires_at IS NULL OR expires_at > NOW())
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

        with conn.cursor() as cur:
            # bulk 조회 3번으로 청크 전체 처리
            all_candidates = _fetch_candidates_bulk(cur, chunk, test_mode=test_mode)
            all_prefs = _fetch_preferences_bulk(cur, chunk)

            unique_vod_ids = list({
                c["vod_id_fk"]
                for cands in all_candidates.values()
                for c in cands
            })
            all_vod_tags = _fetch_vod_tags(cur, unique_vod_ids)

        # Python 메모리 연산 (DB 왕복 없음)
        batch_rows = []
        for uid in chunk:
            candidates = all_candidates.get(uid, [])
            user_prefs = all_prefs.get(uid, {})
            recs = _score_user(candidates, user_prefs, all_vod_tags, beta, top_n, top_k_tags)
            for r in recs:
                batch_rows.append((
                    uid,
                    r["vod_id_fk"],
                    r["rank"],
                    r["score"],
                    json.dumps(r["explanation_tags"], ensure_ascii=False),
                    r["source_engines"],
                ))

        if batch_rows:
            with conn.cursor() as cur:
                args = ",".join(
                    cur.mogrify("(%s,%s,%s,%s,%s::jsonb,%s)", row).decode()
                    for row in batch_rows
                )
                cur.execute(
                    f"""
                    INSERT INTO {dst_table}
                        (user_id_fk, vod_id_fk, rank, score, explanation_tags, source_engines)
                    VALUES {args}
                    ON CONFLICT (user_id_fk, vod_id_fk) DO UPDATE SET
                        rank = EXCLUDED.rank,
                        score = EXCLUDED.score,
                        explanation_tags = EXCLUDED.explanation_tags,
                        source_engines = EXCLUDED.source_engines,
                        generated_at = NOW(),
                        expires_at = NOW() + INTERVAL '7 days'
                    """
                )
                total_inserted += cur.rowcount
            conn.commit()

        processed = min(chunk_start + user_chunk_size, len(user_ids))
        log.info("Progress: %d/%d users", processed, len(user_ids))

    log.info("Phase 3 완료: %d hybrid_recommendation rows", total_inserted)
    return total_inserted
