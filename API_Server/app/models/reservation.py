from datetime import datetime

from pydantic import BaseModel


class ReservationRequest(BaseModel):
    channel: int
    program_name: str
    alert_at: datetime


class ReservationResponse(BaseModel):
    reservation_id: int
    channel: int
    program_name: str
    alert_at: datetime


class ReservationListResponse(BaseModel):
    items: list[ReservationResponse]
    total: int
