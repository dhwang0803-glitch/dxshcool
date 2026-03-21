from fastapi import APIRouter, Depends

from app.models.series import (
    EpisodesResponse,
    ProgressUpdateRequest,
    ProgressUpdateResponse,
    PurchaseCheckResponse,
    PurchaseOptionsResponse,
    SeriesProgressResponse,
)
from app.routers.auth import get_current_user
from app.services import series_service
from app.services.exceptions import (
    EPISODE_NOT_FOUND,
    INVALID_COMPLETION_RATE,
    SERIES_NOT_FOUND,
)

router = APIRouter()


@router.get("/{series_nm}/episodes", response_model=EpisodesResponse)
async def series_episodes(series_nm: str):
    """시리즈 에피소드 목록 (DISTINCT ON 중복 제거)."""
    episodes = await series_service.get_episodes(series_nm)
    if not episodes:
        raise SERIES_NOT_FOUND()
    return EpisodesResponse(
        series_nm=series_nm, episodes=episodes, total=len(episodes)
    )


@router.get(
    "/{series_nm}/progress",
    response_model=SeriesProgressResponse,
)
async def series_progress(
    series_nm: str,
    current_user: str = Depends(get_current_user),
):
    """특정 시리즈 에피소드별 시청 진행 현황."""
    data = await series_service.get_series_progress(current_user, series_nm)
    return SeriesProgressResponse(**data)


@router.post(
    "/{series_nm}/episodes/{asset_nm}/progress",
    response_model=ProgressUpdateResponse,
)
async def update_progress(
    series_nm: str,
    asset_nm: str,
    body: ProgressUpdateRequest,
    current_user: str = Depends(get_current_user),
):
    """에피소드 시청 진행률 기록 (UPSERT)."""
    if body.completion_rate < 0 or body.completion_rate > 100:
        raise INVALID_COMPLETION_RATE()
    result = await series_service.update_episode_progress(
        current_user, series_nm, asset_nm, body.completion_rate
    )
    if not result:
        raise EPISODE_NOT_FOUND()
    return ProgressUpdateResponse(**result)


@router.get(
    "/{series_nm}/purchase-check",
    response_model=PurchaseCheckResponse,
)
async def purchase_check(
    series_nm: str,
    current_user: str = Depends(get_current_user),
):
    """특정 시리즈 구매 여부 + 대여 만료 확인."""
    data = await series_service.check_purchase(current_user, series_nm)
    return PurchaseCheckResponse(**data)


@router.get(
    "/{series_nm}/purchase-options",
    response_model=PurchaseOptionsResponse,
)
async def purchase_options(series_nm: str):
    """구매 옵션 조회 — FOD는 무료(빈 옵션)."""
    data = await series_service.get_purchase_options(series_nm)
    if not data["options"] and not data["is_free"]:
        raise SERIES_NOT_FOUND()
    return PurchaseOptionsResponse(**data)
