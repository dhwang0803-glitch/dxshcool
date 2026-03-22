"""GNB 통합 검색 — 제목/출연진/감독/장르."""

from fastapi import APIRouter, Query

from app.models.search import SearchResponse, SearchResultItem
from app.services import search_service

router = APIRouter()


@router.get("/search", response_model=SearchResponse)
async def vod_search(
    q: str = Query(..., min_length=1, max_length=100, description="검색어"),
):
    """VOD 통합 검색 (asset_nm, cast_lead, director, genre). 최대 8건."""
    results = await search_service.search_vod(q, limit=8)
    items = [SearchResultItem(**r) for r in results]
    return SearchResponse(items=items, total=len(items))
