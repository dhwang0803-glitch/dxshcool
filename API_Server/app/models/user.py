from datetime import datetime

from pydantic import BaseModel


class WatchingItem(BaseModel):
    series_nm: str
    episode_title: str
    poster_url: str | None
    completion_rate: int
    watched_at: datetime


class WatchingResponse(BaseModel):
    items: list[WatchingItem]
    total: int


class UserProfileResponse(BaseModel):
    user_name: str
    point_balance: int


class PointHistoryItem(BaseModel):
    type: str
    amount: int
    description: str
    created_at: datetime


class PointsResponse(BaseModel):
    balance: int
    history: list[PointHistoryItem]


class HistoryItem(BaseModel):
    series_nm: str
    episode_title: str
    poster_url: str | None
    completion_rate: int
    watched_at: datetime


class HistoryResponse(BaseModel):
    items: list[HistoryItem]
    total: int


class UserPurchaseItem(BaseModel):
    series_nm: str
    option_type: str
    points_used: int
    purchased_at: datetime
    expires_at: datetime | None


class UserPurchasesResponse(BaseModel):
    items: list[UserPurchaseItem]
    total: int


class UserWishlistItem(BaseModel):
    series_nm: str
    poster_url: str | None
    created_at: datetime


class UserWishlistResponse(BaseModel):
    items: list[UserWishlistItem]
    total: int
