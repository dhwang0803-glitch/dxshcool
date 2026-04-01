from app.services.base_service import BaseService


class WishlistService(BaseService):
    async def add(self, user_id: str, series_nm: str) -> dict:
        """찜 추가 — ON CONFLICT 무시 (이미 찜한 경우)."""
        await self.execute(
            """
            INSERT INTO public.wishlist (user_id_fk, series_nm)
            VALUES ($1, $2)
            ON CONFLICT (user_id_fk, series_nm) DO NOTHING
            """,
            user_id,
            series_nm,
        )
        return {"series_nm": series_nm, "message": "찜 추가 완료"}

    async def remove(self, user_id: str, series_nm: str) -> dict | None:
        """찜 해제 — 없으면 None 반환."""
        result = await self.execute(
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


wishlist_service = WishlistService()

# 하위 호환
add_wishlist = wishlist_service.add
remove_wishlist = wishlist_service.remove
