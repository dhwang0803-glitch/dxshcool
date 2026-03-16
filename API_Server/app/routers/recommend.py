from fastapi import APIRouter, Depends, Query

from app.models.recommend import RecommendResponse, RecommendItem
from app.routers.auth import get_current_user
from app.services.recommend_service import get_recommendations

router = APIRouter()


@router.get("/{user_id}", response_model=RecommendResponse)
async def recommend(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: str = Depends(get_current_user),
):
    result = await get_recommendations(user_id, limit)
    items = [RecommendItem(**item) for item in result["items"]]
    return RecommendResponse(
        user_id=user_id,
        items=items,
        total=len(items),
        source=result["source"],
    )
