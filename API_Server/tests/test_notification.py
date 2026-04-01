"""
테스트: GET/PATCH/POST/DELETE /user/me/notifications
"""

import pytest


@pytest.mark.asyncio
async def test_notifications_list(async_client, tester_token):
    """알림 목록 조회."""
    resp = await async_client.get(
        "/user/me/notifications",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data
    assert "unread_count" in data
    assert isinstance(data["items"], list)
    for item in data["items"]:
        assert "id" in item
        assert "type" in item
        assert "title" in item
        assert "message" in item
        assert "read" in item
        assert isinstance(item["read"], bool)


@pytest.mark.asyncio
async def test_notifications_read_all(async_client, tester_token):
    """전체 읽음 처리."""
    headers = {"Authorization": f"Bearer {tester_token}"}
    resp = await async_client.post("/user/me/notifications/read-all", headers=headers)
    assert resp.status_code in (200, 204)

    # 전체 읽음 후 미읽 0건
    resp = await async_client.get("/user/me/notifications", headers=headers)
    unread = [n for n in resp.json()["items"] if not n["read"]]
    assert len(unread) == 0


@pytest.mark.asyncio
async def test_notification_not_found(async_client, tester_token):
    """존재하지 않는 알림 읽음 처리 → 404."""
    resp = await async_client.patch(
        "/user/me/notifications/99999999/read",
        headers={"Authorization": f"Bearer {tester_token}"},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_notifications_no_auth(async_client):
    """인증 없음 → 401/403."""
    resp = await async_client.get("/user/me/notifications")
    assert resp.status_code in (401, 403)
