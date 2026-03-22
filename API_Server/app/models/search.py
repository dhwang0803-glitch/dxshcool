from pydantic import BaseModel


class SearchResultItem(BaseModel):
    series_nm: str
    asset_nm: str
    genre: str | None
    ct_cl: str | None
    poster_url: str | None


class SearchResponse(BaseModel):
    items: list[SearchResultItem]
    total: int
