"""
테스트: GET /vod/{asset_id}
- 존재하는 VOD → 200 + 필수 필드
- 존재하지 않는 asset_id → 404
"""

import pytest

from tests.conftest import FIXTURE_VOD_ID


@pytest.mark.asyncio
async def test_vod_detail_ok(async_client):
    """VOD 상세 정상 조회."""
    resp = await async_client.get(f"/vod/{FIXTURE_VOD_ID}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset_id"] == FIXTURE_VOD_ID
    assert "title" in data
    assert "genre" in data
    assert "category" in data
    assert "is_free" in data
    assert isinstance(data["is_free"], bool)


@pytest.mark.asyncio
async def test_vod_detail_not_found(async_client):
    """존재하지 않는 VOD → 404."""
    resp = await async_client.get("/vod/no-such-vod-id")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_vod_detail_url_encoded(async_client):
    """| 포함 asset_id URL 인코딩 처리."""
    from urllib.parse import quote
    encoded = quote(FIXTURE_VOD_ID, safe="")
    resp = await async_client.get(f"/vod/{encoded}")
    assert resp.status_code == 200
