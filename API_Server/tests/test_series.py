"""
테스트: GET /series/{series_nm}/episodes, /progress, /purchase-check, /purchase-options
"""

import pytest
from urllib.parse import quote

from tests.conftest import FIXTURE_SERIES_NM, FIXTURE_USER_ID

_S = quote(FIXTURE_SERIES_NM, safe="")


@pytest.mark.asyncio
async def test_episodes_ok(async_client):
    """에피소드 목록 조회."""
    resp = await async_client.get(f"/series/{_S}/episodes")
    assert resp.status_code == 200
    data = resp.json()
    assert "series_nm" in data
    assert "episodes" in data
    assert isinstance(data["episodes"], list)
    assert len(data["episodes"]) >= 1
    ep = data["episodes"][0]
    assert "episode_title" in ep
    assert "is_free" in ep


@pytest.mark.asyncio
async def test_episodes_not_found(async_client):
    """존재하지 않는 시리즈 → 404."""
    resp = await async_client.get("/series/존재안하는시리즈XYZQ/episodes")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_series_progress(async_client, tester_token):
    """시리즈 시청 진행 현황 (JWT 필요)."""
    resp = await async_client.get(
        f"/series/{_S}/progress",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "series_nm" in data
    assert "episodes" in data


@pytest.mark.asyncio
async def test_series_purchase_check(async_client, tester_token):
    """구매 여부 확인."""
    resp = await async_client.get(
        f"/series/{_S}/purchase-check",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "purchased" in data
    assert isinstance(data["purchased"], bool)


@pytest.mark.asyncio
async def test_series_purchase_options(async_client):
    """구매 옵션 조회 (인증 불필요)."""
    resp = await async_client.get(f"/series/{_S}/purchase-options")
    assert resp.status_code == 200
    data = resp.json()
    assert "series_nm" in data
    assert "is_free" in data
