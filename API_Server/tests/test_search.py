"""
테스트: GET /vod/search?q={query}
- 한글 제목 검색
- 배우명 검색
- 결과 없는 쿼리 → 빈 배열
- q 누락 → 422
"""

import pytest


def _items(data):
    """응답이 list 또는 {"items": [...]} 형태 모두 처리."""
    if isinstance(data, list):
        return data
    return data.get("items", [])


@pytest.mark.asyncio
async def test_search_title_korean(async_client):
    """한글 제목 검색."""
    resp = await async_client.get("/vod/search", params={"q": "킹덤"})
    assert resp.status_code == 200
    items = _items(resp.json())
    assert isinstance(items, list)
    assert len(items) <= 8
    if items:
        item = items[0]
        assert "asset_nm" in item
        assert "ct_cl" in item


@pytest.mark.asyncio
async def test_search_actor(async_client):
    """배우명으로 검색."""
    resp = await async_client.get("/vod/search", params={"q": "최불암"})
    assert resp.status_code == 200
    assert isinstance(_items(resp.json()), list)


@pytest.mark.asyncio
async def test_search_no_result(async_client):
    """결과 없는 쿼리 → 빈 배열."""
    resp = await async_client.get("/vod/search", params={"q": "zzzxxx존재안함쿼리"})
    assert resp.status_code == 200
    assert _items(resp.json()) == []


@pytest.mark.asyncio
async def test_search_missing_query(async_client):
    """q 파라미터 누락 → 422."""
    resp = await async_client.get("/vod/search")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_search_episode_number(async_client):
    """회차 + 제목 조합 검색."""
    resp = await async_client.get("/vod/search", params={"q": "킹덤 2회"})
    assert resp.status_code == 200
    assert isinstance(_items(resp.json()), list)
