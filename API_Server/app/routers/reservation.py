"""시청예약 관리 — 예약 등록/조회/삭제.

alert_at 도래 시 background task가 WebSocket으로 알림 push.
"""

from fastapi import APIRouter, Depends

from app.models.reservation import (
    ReservationListResponse,
    ReservationRequest,
    ReservationResponse,
)
from app.routers.auth import get_current_user
from app.services.db import get_pool

router = APIRouter()


@router.post("", response_model=ReservationResponse)
async def create_reservation(
    body: ReservationRequest,
    current_user: str = Depends(get_current_user),
):
    """시청예약 등록."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO public.watch_reservation
                (user_id_fk, channel, program_name, alert_at)
            VALUES ($1, $2, $3, $4)
            RETURNING reservation_id, channel, program_name, alert_at
            """,
            current_user,
            body.channel,
            body.program_name,
            body.alert_at,
        )
    return ReservationResponse(**dict(row))


@router.get("", response_model=ReservationListResponse)
async def list_reservations(
    current_user: str = Depends(get_current_user),
):
    """시청예약 목록 조회 (미알림 항목만, alert_at ASC)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT reservation_id, channel, program_name, alert_at
            FROM public.watch_reservation
            WHERE user_id_fk = $1 AND notified = FALSE
            ORDER BY alert_at ASC
            """,
            current_user,
        )
    items = [ReservationResponse(**dict(r)) for r in rows]
    return ReservationListResponse(items=items, total=len(items))


@router.delete("/{reservation_id}")
async def cancel_reservation(
    reservation_id: int,
    current_user: str = Depends(get_current_user),
):
    """시청예약 취소."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM public.watch_reservation
            WHERE reservation_id = $1 AND user_id_fk = $2
            """,
            reservation_id,
            current_user,
        )
    return {"deleted": result == "DELETE 1"}
