"""개인화 추천 서비스 — hybrid_recommendation + tag_recommendation 기반."""

from app.services.db import get_pool

# pattern_reason 생성용 템플릿
_REASON_TEMPLATES = {
    "director": "{value} 감독 작품을 즐겨 보셨어요",
    "actor_lead": "{value} 배우 출연작을 자주 보셨어요",
    "actor_guest": "{value} 게스트 출연 회차를 즐겨 보셨어요",
    "genre": "{value} 장르를 자주 시청하셨네요",
    "genre_detail": "{value} 장르를 즐겨 보시네요",
    "rating": "{value} 등급 콘텐츠를 선호하시네요",
}


def _make_reason(tag_category: str, tag_value: str) -> str:
    tpl = _REASON_TEMPLATES.get(tag_category, "{value} 관련 콘텐츠를 즐겨 보셨어요")
    return tpl.format(value=tag_value)


async def get_recommendations(user_id: str) -> dict:
    pool = await get_pool()

    # 1) top_vod: hybrid_recommendation 1위
    top_vod = None
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT r.vod_id_fk, v.asset_nm, v.poster_url
                FROM serving.hybrid_recommendation r
                JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                WHERE r.user_id_fk = $1
                  AND (r.expires_at IS NULL OR r.expires_at > NOW())
                ORDER BY r.rank
                LIMIT 1
                """,
                user_id,
            )
            if row:
                top_vod = {
                    "series_id": row["vod_id_fk"],
                    "asset_nm": row["asset_nm"],
                    "poster_url": row["poster_url"],
                }
    except Exception:
        pass

    # 2) patterns: tag_recommendation (top 5 태그 × top 10 VOD)
    patterns = []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT tr.tag_category, tr.tag_value, tr.tag_rank,
                       tr.tag_affinity, tr.vod_id_fk, tr.vod_rank, tr.vod_score,
                       v.asset_nm, v.poster_url
                FROM serving.tag_recommendation tr
                JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                WHERE tr.user_id_fk = $1
                  AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                ORDER BY tr.tag_rank, tr.vod_rank
                """,
                user_id,
            )

        # tag_rank별 그룹핑
        grouped: dict[int, dict] = {}
        for r in rows:
            rank = r["tag_rank"]
            if rank not in grouped:
                grouped[rank] = {
                    "pattern_rank": rank,
                    "pattern_reason": _make_reason(r["tag_category"], r["tag_value"]),
                    "vod_list": [],
                }
            grouped[rank]["vod_list"].append({
                "series_id": r["vod_id_fk"],
                "asset_nm": r["asset_nm"],
                "poster_url": r["poster_url"],
                "score": r["vod_score"],
            })

        patterns = [grouped[k] for k in sorted(grouped.keys())]
    except Exception:
        pass

    if top_vod or patterns:
        return {"top_vod": top_vod, "patterns": patterns, "source": "personalized"}

    # Fallback: popular 기반
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT pr.vod_id_fk, pr.score, pr.ct_cl,
                       v.asset_nm, v.poster_url
                FROM serving.popular_recommendation pr
                JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
                ORDER BY pr.score DESC
                LIMIT 10
                """,
            )

        if rows:
            top_vod = {
                "series_id": rows[0]["vod_id_fk"],
                "asset_nm": rows[0]["asset_nm"],
                "poster_url": rows[0]["poster_url"],
            }
            patterns = [{
                "pattern_rank": 1,
                "pattern_reason": "지금 인기 있는 콘텐츠",
                "vod_list": [
                    {
                        "series_id": r["vod_id_fk"],
                        "asset_nm": r["asset_nm"],
                        "poster_url": r["poster_url"],
                        "score": r["score"],
                    }
                    for r in rows[1:]
                ],
            }]
    except Exception:
        pass

    return {"top_vod": top_vod, "patterns": patterns, "source": "popular_fallback"}
