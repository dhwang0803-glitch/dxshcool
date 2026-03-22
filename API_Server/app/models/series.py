from datetime import datetime

from pydantic import BaseModel


class EpisodeItem(BaseModel):
    episode_title: str
    category: str | None
    poster_url: str | None
    is_free: bool


class EpisodesResponse(BaseModel):
    series_nm: str
    episodes: list[EpisodeItem]
    total: int


class EpisodeProgressItem(BaseModel):
    episode_title: str
    completion_rate: int
    watched_at: datetime | None


class SeriesProgressResponse(BaseModel):
    series_nm: str
    last_episode: str | None
    last_completion_rate: int | None
    episodes: list[EpisodeProgressItem]


class ProgressUpdateRequest(BaseModel):
    completion_rate: int


class ProgressUpdateResponse(BaseModel):
    episode_title: str
    completion_rate: int
    watched_at: datetime | None


class PurchaseCheckResponse(BaseModel):
    series_nm: str
    purchased: bool
    option_type: str | None
    expires_at: datetime | None
    is_expired: bool | None


class PurchaseOption(BaseModel):
    option_type: str
    points: int
    duration: str | None


class PurchaseOptionsResponse(BaseModel):
    series_nm: str
    is_free: bool
    options: list[PurchaseOption]
