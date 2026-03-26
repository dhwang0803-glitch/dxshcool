"""
테스트: GET /home/banner, /home/sections, /home/sections/{user_id}
"""

import pytest

from tests.conftest import FIXTURE_USER_ID


@pytest.mark.asyncio
async def test_home_banner_no_auth(async_client):
    """비로그인 배너 — items 목록 반환."""
    resp = await async_client.get("/home/banner")
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data


@pytest.mark.asyncio
async def test_home_banner_with_auth(async_client, tester_token):
    """로그인 배너 — items 목록 반환."""
    resp = await async_client.get(
        "/home/banner",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    assert "total" in data


@pytest.mark.asyncio
async def test_home_sections(async_client):
    """CT_CL 4종 인기 섹션."""
    resp = await async_client.get("/home/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert "sections" in data
    assert len(data["sections"]) >= 1
    for section in data["sections"]:
        assert "ct_cl" in section
        assert "vod_list" in section
        assert isinstance(section["vod_list"], list)


@pytest.mark.asyncio
async def test_home_sections_personalized(async_client, tester_token):
    """개인화 섹션 — 장르 시청 비중 기반."""
    resp = await async_client.get(
        f"/home/sections/{FIXTURE_USER_ID}",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "sections" in data
    sections = data["sections"]
    assert len(sections) >= 1
    for s in sections:
        assert "genre" in s
        assert "view_ratio" in s
        assert "vod_list" in s
