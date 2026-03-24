from datetime import datetime

from pydantic import BaseModel


class PurchaseRequest(BaseModel):
    series_nm: str
    option_type: str
    points_used: int


class PurchaseResponse(BaseModel):
    series_nm: str
    option_type: str
    points_used: int
    remaining_points: int
    expires_at: datetime | None
