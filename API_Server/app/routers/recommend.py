from fastapi import APIRouter, Depends

from app.models.recommend import (
    PatternItem,
    PatternVodItem,
    RecommendResponse,
    TopVod,
)
from app.routers.auth import get_current_user
from app.services.recommend_service import get_recommendations

router = APIRouter()


@router.get("/{user_id}", response_model=RecommendResponse)
async def recommend(
    user_id: str,
    current_user: str = Depends(get_current_user),
):
    """개인화 추천 — top_vod + patterns(태그별 그룹핑)."""
    result = await get_recommendations(user_id)

    top_vod = TopVod(**result["top_vod"]) if result["top_vod"] else None

    patterns = [
        PatternItem(
            pattern_rank=p["pattern_rank"],
            pattern_reason=p["pattern_reason"],
            vod_list=[PatternVodItem(**v) for v in p["vod_list"]],
        )
        for p in result["patterns"]
    ]

    return RecommendResponse(
        user_id=user_id,
        top_vod=top_vod,
        patterns=patterns,
        source=result["source"],
    )
