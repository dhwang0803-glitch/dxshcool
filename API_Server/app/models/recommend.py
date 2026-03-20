from pydantic import BaseModel


class RecommendItem(BaseModel):
    asset_id: str
    title: str
    genre: str | None
    poster_url: str | None
    score: float | None
    rank: int | None
    recommendation_type: str | None  # 'HYBRID' | 'COLLABORATIVE' | 'VISUAL_SIMILARITY' | 'CONTENT_BASED' | 'POPULAR'


class RecommendResponse(BaseModel):
    user_id: str
    items: list[RecommendItem]
    total: int
    source: str  # 'personalized' | 'popular_fallback'


class SimilarVodItem(BaseModel):
    asset_id: str
    title: str
    genre: str | None
    poster_url: str | None
    score: float | None
    rank: int | None


class SimilarVodResponse(BaseModel):
    base_asset_id: str
    items: list[SimilarVodItem]
    total: int
    source: str  # 'vector_similarity' | 'genre_fallback'
