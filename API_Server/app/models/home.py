from pydantic import BaseModel


class BannerItem(BaseModel):
    series_nm: str
    title: str
    poster_url: str | None
    category: str | None
    score: float | None


class BannerResponse(BaseModel):
    items: list[BannerItem]
    total: int


class SectionVodItem(BaseModel):
    series_nm: str
    title: str
    poster_url: str | None
    score: float | None
    rank: int | None


class SectionItem(BaseModel):
    ct_cl: str
    vod_list: list[SectionVodItem]


class SectionsResponse(BaseModel):
    sections: list[SectionItem]
