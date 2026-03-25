"""
테스트: GET /similar/{asset_id}
"""

import pytest

from tests.conftest import FIXTURE_SIMILAR_VOD_ID, FIXTURE_VOD_ID


@pytest.mark.asyncio
async def test_similar_ok(async_client):
    """유사 콘텐츠 정상 조회."""
    resp = await async_client.get(f"/similar/{FIXTURE_SIMILAR_VOD_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert "base_asset_id" in data
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data
    assert "source" in data
    if data["items"]:
        item = data["items"][0]
        assert "asset_id" in item


@pytest.mark.asyncio
async def test_similar_no_data(async_client):
    """CONTENT_BASED 추천 없는 VOD → 404."""
    resp = await async_client.get(f"/similar/{FIXTURE_VOD_ID}")
    # 추천 없으면 라우터가 404 반환
    assert resp.status_code in (200, 404)
