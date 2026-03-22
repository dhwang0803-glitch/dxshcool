"""GNB 통합 검색 — pg_trgm 기반 asset_nm/cast_lead/director/genre 검색."""

from app.services.db import get_pool


async def search_vod(query: str, limit: int = 8) -> list[dict]:
    """VOD 통합 검색. series_nm 기준 중복 제거, 최대 limit건."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (COALESCE(series_nm, asset_nm))
                   COALESCE(series_nm, asset_nm) AS series_nm,
                   asset_nm, genre, ct_cl, poster_url
            FROM public.vod
            WHERE (COALESCE(asset_nm, '') || ' ' ||
                   COALESCE(cast_lead, '') || ' ' ||
                   COALESCE(director, '') || ' ' ||
                   COALESCE(genre, ''))
                  ILIKE '%' || $1 || '%'
            ORDER BY COALESCE(series_nm, asset_nm), asset_nm
            LIMIT $2
            """,
            query,
            limit,
        )
    return [dict(r) for r in rows]
