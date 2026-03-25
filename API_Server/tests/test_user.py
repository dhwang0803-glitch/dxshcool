"""
테스트: GET /user/me/profile, /watching, /history, /purchases, /wishlist, /points
"""

import pytest


@pytest.mark.asyncio
async def test_user_profile(async_client, tester_token):
    """유저 프로필 조회."""
    resp = await async_client.get(
        "/user/me/profile",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "point_balance" in data
    assert isinstance(data["point_balance"], int)


@pytest.mark.asyncio
async def test_user_watching(async_client, tester_token):
    """시청 중인 콘텐츠 목록."""
    resp = await async_client.get(
        "/user/me/watching",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_user_history(async_client, tester_token):
    """시청 내역 목록."""
    resp = await async_client.get(
        "/user/me/history",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_user_purchases(async_client, tester_token):
    """구매 내역 목록."""
    resp = await async_client.get(
        "/user/me/purchases",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_user_wishlist(async_client, tester_token):
    """찜 목록 조회."""
    resp = await async_client.get(
        "/user/me/wishlist",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)


@pytest.mark.asyncio
async def test_user_points(async_client, tester_token):
    """포인트 잔액 + 내역."""
    resp = await async_client.get(
        "/user/me/points",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "balance" in data
    assert "history" in data


@pytest.mark.asyncio
async def test_user_no_auth(async_client):
    """인증 없이 /user/me/* 요청 → 401/403."""
    for path in ["/user/me/profile", "/user/me/watching", "/user/me/history"]:
        resp = await async_client.get(path)
        assert resp.status_code in (401, 403), f"{path} → {resp.status_code}"
