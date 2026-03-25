"""
테스트: GET /recommend/{user_id}
- JWT 없이 요청 → 401/403
- 유효한 user_id + JWT → 200 + top_vod / patterns 구조
- user_id와 토큰 불일치는 허용 (API가 user_id 파라미터 기준)
"""

import pytest

from tests.conftest import FIXTURE_USER_ID


@pytest.mark.asyncio
async def test_recommend_no_auth(async_client):
    """JWT 없음 → 401/403."""
    resp = await async_client.get(f"/recommend/{FIXTURE_USER_ID}")
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_recommend_ok(async_client, tester_token):
    """정상 추천 조회 — 응답 구조 검증."""
    resp = await async_client.get(
        f"/recommend/{FIXTURE_USER_ID}",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == FIXTURE_USER_ID
    assert "top_vod" in data
    assert "patterns" in data
    assert "source" in data
    assert isinstance(data["patterns"], list)


@pytest.mark.asyncio
async def test_recommend_patterns_structure(async_client, tester_token):
    """patterns 내부 구조 검증."""
    resp = await async_client.get(
        f"/recommend/{FIXTURE_USER_ID}",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    patterns = resp.json()["patterns"]
    for p in patterns:
        assert "pattern_rank" in p
        assert "pattern_reason" in p
        assert "vod_list" in p
        assert isinstance(p["vod_list"], list)
        for v in p["vod_list"]:
            assert "series_id" in v
            assert "asset_nm" in v


@pytest.mark.asyncio
async def test_recommend_unknown_user(async_client, tester_token):
    """추천 데이터 없는 user — fallback 또는 빈 결과 (200)."""
    resp = await async_client.get(
        "/recommend/unknown-user-000",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    # 404 또는 200(빈 결과) 모두 허용
    assert resp.status_code in (200, 404)
