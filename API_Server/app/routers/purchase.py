from fastapi import APIRouter, Depends, HTTPException

from app.models.purchase import PurchaseRequest, PurchaseResponse
from app.routers.auth import get_current_user
from app.services import purchase_service

router = APIRouter()


@router.post("", response_model=PurchaseResponse)
async def create_purchase(
    body: PurchaseRequest,
    current_user: str = Depends(get_current_user),
):
    """포인트 차감 + purchase_history + point_history 트랜잭션."""
    if body.option_type not in ("rental", "permanent"):
        raise HTTPException(status_code=400, detail="option_type: rental 또는 permanent")
    if body.points_used <= 0:
        raise HTTPException(status_code=400, detail="points_used는 양수여야 합니다")

    try:
        result = await purchase_service.create_purchase(
            current_user, body.series_nm, body.option_type, body.points_used
        )
    except ValueError as e:
        raise HTTPException(status_code=402, detail=str(e))

    return PurchaseResponse(**result)
