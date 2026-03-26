"""
테스트: POST /auth/token
- 테스터 12명 전원 토큰 발급 성공
- 존재하지 않는 user_id → 404
- user_id 누락 → 422
"""

import pytest

from tests.conftest import TESTERS


@pytest.mark.asyncio
async def test_token_all_testers(async_client):
    """테스터 12명 전원 토큰 발급 성공."""
    for label, sha2 in TESTERS.items():
        resp = await async_client.post("/auth/token", json={"user_id": sha2})
        assert resp.status_code == 200, f"[{label}] {resp.text}"
        data = resp.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_token_unknown_user(async_client):
    """존재하지 않는 user_id → 404."""
    resp = await async_client.post("/auth/token", json={"user_id": "no-such-user"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_token_missing_body(async_client):
    """user_id 누락 → 422."""
    resp = await async_client.post("/auth/token", json={})
    assert resp.status_code == 422
