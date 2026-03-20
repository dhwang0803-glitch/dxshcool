from fastapi import APIRouter

from app.models.home import BannerResponse, SectionsResponse
from app.services import home_service

router = APIRouter()


@router.get("/banner", response_model=BannerResponse)
async def home_banner():
    """히어로 배너 Top 5 (Hybrid score 내림차순, fallback → popular)."""
    items = await home_service.get_banner(limit=5)
    return BannerResponse(items=items, total=len(items))


@router.get("/sections", response_model=SectionsResponse)
async def home_sections():
    """CT_CL 4종 × Top 20 인기 추천."""
    sections = await home_service.get_sections()
    return SectionsResponse(sections=sections)
