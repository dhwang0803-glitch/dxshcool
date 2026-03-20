from fastapi import APIRouter, Depends, HTTPException

from app.models.wishlist import (
    WishlistAddRequest,
    WishlistAddResponse,
    WishlistRemoveResponse,
)
from app.routers.auth import get_current_user
from app.services import wishlist_service

router = APIRouter()


@router.post("", response_model=WishlistAddResponse)
async def add_wishlist(
    body: WishlistAddRequest,
    current_user: str = Depends(get_current_user),
):
    """찜 추가 (이미 존재 시 무시)."""
    result = await wishlist_service.add_wishlist(current_user, body.series_nm)
    return WishlistAddResponse(**result)


@router.delete("/{series_nm}", response_model=WishlistRemoveResponse)
async def remove_wishlist(
    series_nm: str,
    current_user: str = Depends(get_current_user),
):
    """찜 해제."""
    result = await wishlist_service.remove_wishlist(current_user, series_nm)
    if not result:
        raise HTTPException(status_code=404, detail="찜 목록에 없는 시리즈입니다")
    return WishlistRemoveResponse(**result)
