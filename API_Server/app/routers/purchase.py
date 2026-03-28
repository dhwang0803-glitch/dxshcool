from fastapi import APIRouter, Depends

from app.models.purchase import PurchaseRequest, PurchaseResponse
from app.routers.auth import get_current_user
from app.services import purchase_service
from app.services.exceptions import INVALID_OPTION_TYPE, INVALID_POINTS_AMOUNT

router = APIRouter()


@router.post("", response_model=PurchaseResponse)
async def create_purchase(
    body: PurchaseRequest,
    current_user: str = Depends(get_current_user),
):
    """포인트 차감 + purchase_history + point_history 트랜잭션."""
    if body.option_type not in ("rental", "permanent"):
        raise INVALID_OPTION_TYPE()
    if body.points_used <= 0:
        raise INVALID_POINTS_AMOUNT()

    result = await purchase_service.create_purchase(
        current_user, body.series_nm, body.option_type, body.points_used
    )
    return PurchaseResponse(**result)
