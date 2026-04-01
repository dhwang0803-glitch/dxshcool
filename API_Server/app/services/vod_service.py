from app.services.base_service import BaseService


class VodService(BaseService):
    async def get_detail(self, asset_id: str) -> dict | None:
        return await self.query_one(
            """
            SELECT full_asset_id, asset_nm, genre, ct_cl,
                   director, cast_lead, cast_guest, smry,
                   rating, release_date, poster_url, asset_prod,
                   youtube_video_id
            FROM public.vod
            WHERE full_asset_id = $1
            """,
            asset_id,
        )


vod_service = VodService()

# 하위 호환: 기존 import 경로 유지
get_vod_detail = vod_service.get_detail
