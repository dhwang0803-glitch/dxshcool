from fastapi import APIRouter

from app.models.vod import VodDetailResponse
from app.services.exceptions import VOD_NOT_FOUND
from app.services.vod_service import get_vod_detail

router = APIRouter()


@router.get("/{asset_id}", response_model=VodDetailResponse)
async def vod_detail(asset_id: str):
    vod = await get_vod_detail(asset_id)
    if vod is None:
        raise VOD_NOT_FOUND()
    yt_id = vod.get("youtube_video_id")
    youtube_url = f"https://www.youtube.com/embed/{yt_id}" if yt_id else None

    return VodDetailResponse(
        asset_id=vod["full_asset_id"],
        title=vod["asset_nm"],
        genre=vod["genre"],
        category=vod["ct_cl"],
        director=vod["director"],
        cast_lead=vod["cast_lead"],
        cast_guest=vod["cast_guest"],
        summary=vod["smry"],
        rating=vod["rating"],
        release_year=vod["release_date"].year if vod["release_date"] else None,
        poster_url=vod["poster_url"],
        is_free=vod.get("asset_prod") == "FOD",
        youtube_url=youtube_url,
    )
