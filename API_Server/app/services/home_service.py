from app.services.db import get_pool


async def get_banner(limit: int = 5) -> list[dict]:
    """히어로 배너 Top N — hybrid_recommendation 또는 popular fallback."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # hybrid_recommendation 시도
        try:
            rows = await conn.fetch(
                """
                SELECT r.vod_id_fk, r.score,
                       v.series_nm, v.asset_nm, v.poster_url, v.ct_cl
                FROM serving.hybrid_recommendation r
                JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                ORDER BY r.score DESC
                LIMIT $1
                """,
                limit,
            )
        except Exception:
            rows = []

        if not rows:
            # popular fallback
            rows = await conn.fetch(
                """
                SELECT pr.vod_id_fk, pr.score,
                       v.series_nm, v.asset_nm, v.poster_url, v.ct_cl
                FROM serving.popular_recommendation pr
                JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
                ORDER BY pr.score DESC
                LIMIT $1
                """,
                limit,
            )

    seen = set()
    items = []
    for r in rows:
        nm = r["series_nm"] or r["asset_nm"]
        if nm in seen:
            continue
        seen.add(nm)
        items.append(
            {
                "series_nm": nm,
                "title": r["asset_nm"],
                "poster_url": r["poster_url"],
                "category": r["ct_cl"],
                "score": r["score"],
            }
        )
    return items[:limit]


async def get_sections() -> list[dict]:
    """CT_CL 4종 × Top 20 인기 추천."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pr.ct_cl, pr.rank, pr.score, pr.vod_id_fk,
                   v.series_nm, v.asset_nm, v.poster_url
            FROM serving.popular_recommendation pr
            JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
            ORDER BY pr.ct_cl, pr.rank
            """
        )

    sections: dict[str, list] = {}
    for r in rows:
        ct = r["ct_cl"]
        if ct not in sections:
            sections[ct] = []
        sections[ct].append(
            {
                "series_nm": r["series_nm"] or r["asset_nm"],
                "title": r["asset_nm"],
                "poster_url": r["poster_url"],
                "score": r["score"],
                "rank": r["rank"],
            }
        )

    return [{"ct_cl": ct, "vod_list": vods} for ct, vods in sections.items()]
