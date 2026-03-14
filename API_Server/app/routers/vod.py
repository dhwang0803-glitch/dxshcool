from fastapi import APIRouter, HTTPException

from app.models.vod import VodDetailResponse
from app.services.vod_service import get_vod_detail

router = APIRouter()


@router.get("/{asset_id}", response_model=VodDetailResponse)
async def vod_detail(asset_id: str):
    vod = await get_vod_detail(asset_id)
    if vod is None:
        raise HTTPException(status_code=404, detail="VOD not found")
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
        release_date=vod["release_date"],
        poster_url=vod["poster_url"],
    )
