from fastapi import APIRouter, HTTPException, Query

from app.models.recommend import SimilarVodResponse, SimilarVodItem
from app.services.similar_service import get_similar_vods

router = APIRouter()


@router.get("/{asset_id}", response_model=SimilarVodResponse)
async def similar_vods(
    asset_id: str,
    limit: int = Query(default=10, ge=1, le=50),
):
    result = await get_similar_vods(asset_id, limit)
    if not result["items"]:
        raise HTTPException(status_code=404, detail="No similar VOD found")
    items = [SimilarVodItem(**item) for item in result["items"]]
    return SimilarVodResponse(
        base_asset_id=asset_id,
        items=items,
        total=len(items),
        source=result["source"],
    )
