from datetime import datetime

from pydantic import BaseModel


class NotificationItem(BaseModel):
    id: int
    type: str
    title: str
    message: str
    image_url: str | None
    read: bool
    created_at: datetime


class NotificationListResponse(BaseModel):
    items: list[NotificationItem]
    total: int
    unread_count: int
