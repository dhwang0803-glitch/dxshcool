from app.services.db import get_pool


async def get_recommendations(user_id: str, limit: int = 10) -> dict:
    pool = await get_pool()

    # Primary: serving.vod_recommendation
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.vod_id_fk AS asset_id, r.rank, r.score,
                       r.recommendation_type, v.asset_nm AS title,
                       v.genre, v.poster_url
                FROM serving.vod_recommendation r
                JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                WHERE r.user_id_fk = $1
                ORDER BY r.rank
                LIMIT $2
                """,
                user_id, limit,
            )
        if rows:
            return {"items": [dict(r) for r in rows], "source": "personalized"}
    except Exception:
        pass  # serving 스키마 미생성 시 fallback으로 전환

    # Fallback: serving.mv_vod_watch_stats 인기 콘텐츠
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT s.vod_id_fk AS asset_id, v.asset_nm AS title,
                       v.genre, v.poster_url,
                       NULL::float AS score,
                       ROW_NUMBER() OVER (ORDER BY s.total_watch_count DESC)::int AS rank,
                       'POPULAR' AS recommendation_type
                FROM serving.mv_vod_watch_stats s
                JOIN public.vod v ON s.vod_id_fk = v.full_asset_id
                ORDER BY s.total_watch_count DESC
                LIMIT $1
                """,
                limit,
            )
        return {"items": [dict(r) for r in rows], "source": "popular_fallback"}
    except Exception:
        pass

    return {"items": [], "source": "popular_fallback"}
