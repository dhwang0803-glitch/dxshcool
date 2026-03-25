from app.services.db import get_pool


async def get_vod_detail(asset_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT full_asset_id, asset_nm, genre, ct_cl,
                   director, cast_lead, cast_guest, smry,
                   rating, release_date, poster_url, asset_prod
            FROM public.vod
            WHERE full_asset_id = $1
            """,
            asset_id,
        )
    return dict(row) if row else None
