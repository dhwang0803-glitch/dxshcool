from app.services.db import get_pool


async def add_wishlist(user_id: str, series_nm: str) -> dict:
    """찜 추가 — ON CONFLICT 무시 (이미 찜한 경우)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.wishlist (user_id_fk, series_nm)
            VALUES ($1, $2)
            ON CONFLICT (user_id_fk, series_nm) DO NOTHING
            """,
            user_id,
            series_nm,
        )
    return {"series_nm": series_nm, "message": "찜 추가 완료"}


async def remove_wishlist(user_id: str, series_nm: str) -> dict | None:
    """찜 해제 — 없으면 None 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM public.wishlist
            WHERE user_id_fk = $1 AND series_nm = $2
            """,
            user_id,
            series_nm,
        )
    if result == "DELETE 0":
        return None
    return {"series_nm": series_nm, "message": "찜 해제 완료"}
