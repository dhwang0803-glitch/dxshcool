from fastapi import APIRouter, Depends, Query

from app.models.user import (
    HistoryResponse,
    PointsResponse,
    UserProfileResponse,
    UserPurchasesResponse,
    UserWishlistResponse,
    WatchingResponse,
)
from app.routers.auth import get_current_user
from app.services import user_service
from app.services.exceptions import PROFILE_NOT_FOUND

router = APIRouter()


@router.get("/me/watching", response_model=WatchingResponse)
async def watching(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: str = Depends(get_current_user),
):
    """시청 중인 콘텐츠 (진행률 1~99%, 최신순)."""
    items = await user_service.get_watching(current_user, limit)
    return WatchingResponse(items=items, total=len(items))


@router.get("/me/profile", response_model=UserProfileResponse)
async def profile(current_user: str = Depends(get_current_user)):
    """유저 프로필 — user_name(sha2_hash 앞 5자), point_balance, coupon_count."""
    data = await user_service.get_profile(current_user)
    if not data:
        raise PROFILE_NOT_FOUND()
    return UserProfileResponse(**data)


@router.get("/me/points", response_model=PointsResponse)
async def points(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: str = Depends(get_current_user),
):
    """포인트 잔액 + 최근 내역."""
    data = await user_service.get_points(current_user, limit)
    return PointsResponse(**data)


@router.get("/me/history", response_model=HistoryResponse)
async def history(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: str = Depends(get_current_user),
):
    """시청 내역 — episode_progress 기반 (watch_history 미노출)."""
    items = await user_service.get_history(current_user, limit)
    return HistoryResponse(items=items, total=len(items))


@router.get("/me/purchases", response_model=UserPurchasesResponse)
async def purchases(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: str = Depends(get_current_user),
):
    """구매 내역."""
    items = await user_service.get_purchases(current_user, limit)
    return UserPurchasesResponse(items=items, total=len(items))


@router.get("/me/wishlist", response_model=UserWishlistResponse)
async def wishlist(current_user: str = Depends(get_current_user)):
    """찜 목록 (created_at DESC)."""
    items = await user_service.get_wishlist(current_user)
    return UserWishlistResponse(items=items, total=len(items))
