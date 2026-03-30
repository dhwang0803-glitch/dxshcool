from fastapi import APIRouter, Depends

from app.models.home import (
    BannerResponse,
    PersonalizedSectionsResponse,
    SectionsResponse,
)
from app.routers.auth import get_current_user, get_optional_user
from app.services import home_service

router = APIRouter()


@router.get("/banner", response_model=BannerResponse)
async def home_banner(
    current_user: str | None = Depends(get_optional_user),
):
    """히어로 배너 3단 구조.

    로그인: personalized(5) + popular(5) + hybrid(10)
    비로그인: popular(5)
    """
    items = await home_service.get_banner()
    return BannerResponse(items=items, total=len(items))


@router.get("/sections", response_model=SectionsResponse)
async def home_sections():
    """CT_CL 4종 × Top 20 인기 추천 (비로그인/신규 유저 fallback용)."""
    sections = await home_service.get_sections()
    return SectionsResponse(sections=sections)


@router.get("/sections/{user_id}", response_model=PersonalizedSectionsResponse)
async def home_sections_personalized(
    user_id: str,
    current_user: str = Depends(get_current_user),
):
    """개인화 섹션 — 장르별 시청 비중 내림차순 + 미시청 장르 도전.

    시청 이력 없으면 CT_CL 4종 고정 응답으로 fallback.
    """
    personalized = await home_service.get_personalized_sections(user_id)
    if personalized is None:
        # fallback: 기존 CT_CL 4종
        sections = await home_service.get_sections()
        fallback = [
            {"genre": s["ct_cl"], "view_ratio": 0, "vod_list": [
                {"series_nm": v["series_nm"], "asset_nm": v["title"], "poster_url": v["poster_url"]}
                for v in s["vod_list"]
            ]}
            for s in sections
        ]
        return PersonalizedSectionsResponse(sections=fallback)
    return PersonalizedSectionsResponse(sections=personalized)
