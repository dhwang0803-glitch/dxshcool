"""Phase 3: CF + Vector 후보 리랭킹 → hybrid_recommendation 적재.

serving.vod_recommendation 후보 × vod_tag × user_preference
→ hybrid_score 계산 → 상위 10건 + explanation_tags 생성
→ serving.hybrid_recommendation UPSERT
"""

import json
import logging
from statistics import mean

log = logging.getLogger(__name__)


def _fetch_user_candidates(cur, user_id: str) -> list[dict]:
    """유저의 vod_recommendation 후보 조회 (CF + Vector + Content-based).

    시리즈 단위 중복 제거: 같은 series_nm의 에피소드 중 최고 score 1건만 유지.
    """
    cur.execute(
        """
        SELECT r.vod_id_fk, r.score, r.recommendation_type,
               v.series_nm
        FROM serving.vod_recommendation r
        JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
        WHERE r.user_id_fk = %s
          AND (r.expires_at IS NULL OR r.expires_at > NOW())
        ORDER BY r.score DESC
        """,
        (user_id,),
    )
    seen_series: set[str] = set()
    candidates = []
    for row in cur.fetchall():
        vid, score, rec_type, series_nm = row
        nm = series_nm or vid
        if nm in seen_series:
            continue
        seen_series.add(nm)
        candidates.append({
            "vod_id_fk": vid,
            "score": score,
            "recommendation_type": rec_type,
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


def rerank_user(
    cur,
    user_id: str,
    beta: float = 0.6,
    top_n: int = 10,
    top_k_tags: int = 3,
) -> list[dict]:
    """단일 유저의 후보를 리랭킹하여 상위 top_n 추천 생성.

    Returns:
        [{"vod_id_fk", "rank", "score", "explanation_tags", "source_engines"}, ...]
    """
    candidates = _fetch_user_candidates(cur, user_id)
    if not candidates:
        return []

    user_prefs = _fetch_user_preferences(cur, user_id)
    if not user_prefs:
        # 선호 프로필 없으면 원본 스코어 그대로 사용
        results = []
        for i, c in enumerate(candidates[:top_n], 1):
            results.append({
                "vod_id_fk": c["vod_id_fk"],
                "rank": i,
                "score": c["score"],
                "explanation_tags": [],
                "source_engines": [c["recommendation_type"]],
            })
        return results

    vod_ids = [c["vod_id_fk"] for c in candidates]
    vod_tags = _fetch_vod_tags(cur, vod_ids)

    scored = []
    for c in candidates:
        vid = c["vod_id_fk"]
        tags = vod_tags.get(vid, [])

        # 태그 매칭: VOD 태그 × 유저 선호
        matched = []
        for cat, val, conf in tags:
            aff = user_prefs.get((cat, val))
            if aff is not None:
                matched.append({"category": cat, "value": val, "affinity": aff})

        # affinity 내림차순 정렬
        matched.sort(key=lambda x: x["affinity"], reverse=True)

        # tag_overlap_score: 상위 k개 매칭 태그 affinity 평균
        top_affinities = [m["affinity"] for m in matched[:top_k_tags]]
        tag_overlap_score = mean(top_affinities) if top_affinities else 0.0

        # hybrid_score
        hybrid_score = beta * c["score"] + (1 - beta) * tag_overlap_score

        scored.append({
            "vod_id_fk": vid,
            "hybrid_score": min(hybrid_score, 1.0),
            "explanation_tags": matched[:5],  # 설명용 상위 5개
            "source_engines": [c["recommendation_type"]],
        })

    # hybrid_score 내림차순 정렬 → 상위 top_n
    scored.sort(key=lambda x: x["hybrid_score"], reverse=True)

    results = []
    for i, s in enumerate(scored[:top_n], 1):
        results.append({
            "vod_id_fk": s["vod_id_fk"],
            "rank": i,
            "score": round(s["hybrid_score"], 6),
            "explanation_tags": s["explanation_tags"],
            "source_engines": s["source_engines"],
        })
    return results


def run_hybrid_reranking(
    conn,
    beta: float = 0.6,
    top_n: int = 10,
    top_k_tags: int = 3,
    user_chunk_size: int = 1000,
) -> int:
    """전체 유저 리랭킹 → hybrid_recommendation 적재.

    Returns:
        총 적재 레코드 수
    """
    log.info("Phase 3: Hybrid reranking (beta=%.2f, top_n=%d)", beta, top_n)

    with conn.cursor() as cur:
        # 대상 유저 조회 (vod_recommendation에 후보가 있는 유저)
        cur.execute(
            """
            SELECT DISTINCT user_id_fk
            FROM serving.vod_recommendation
            WHERE user_id_fk IS NOT NULL
              AND (expires_at IS NULL OR expires_at > NOW())
            """
        )
        user_ids = [r[0] for r in cur.fetchall()]

    log.info("Target users: %d", len(user_ids))
    if not user_ids:
        return 0

    # 기존 데이터 삭제
    with conn.cursor() as cur:
        cur.execute("DELETE FROM serving.hybrid_recommendation")
        log.info("Cleared %d existing hybrid_recommendation rows", cur.rowcount)

    total_inserted = 0
    for chunk_start in range(0, len(user_ids), user_chunk_size):
        chunk = user_ids[chunk_start : chunk_start + user_chunk_size]
        batch_rows = []

        with conn.cursor() as cur:
            for uid in chunk:
                recs = rerank_user(cur, uid, beta, top_n, top_k_tags)
                for r in recs:
                    batch_rows.append((
                        uid,
                        r["vod_id_fk"],
                        r["rank"],
                        r["score"],
                        json.dumps(r["explanation_tags"], ensure_ascii=False),
                        r["source_engines"],
                    ))

        # 배치 INSERT
        if batch_rows:
            with conn.cursor() as cur:
                args = ",".join(
                    cur.mogrify("(%s,%s,%s,%s,%s::jsonb,%s)", row).decode()
                    for row in batch_rows
                )
                cur.execute(
                    f"""
                    INSERT INTO serving.hybrid_recommendation
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
