from pydantic import BaseModel


# --- /recommend/{user_id} patterns 구조 ---

class TopVod(BaseModel):
    series_id: str
    asset_nm: str
    poster_url: str | None
    rec_sentence: str | None = None  # 세그먼트 맞춤 문구


class PatternVodItem(BaseModel):
    series_id: str
    asset_nm: str
    poster_url: str | None
    score: float | None


class PatternItem(BaseModel):
    pattern_rank: int
    pattern_reason: str
    vod_list: list[PatternVodItem]


class RecommendResponse(BaseModel):
    user_id: str
    top_vod: TopVod | None
    patterns: list[PatternItem]
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
