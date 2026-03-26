from pydantic import BaseModel


class VodDetailResponse(BaseModel):
    asset_id: str
    title: str
    genre: str | None
    category: str | None
    director: str | None
    cast_lead: str | None
    cast_guest: str | None
    summary: str | None
    rating: str | None
    release_year: int | None
    poster_url: str | None
    youtube_url: str | None
    is_free: bool
