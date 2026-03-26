"""
테스트: POST/DELETE /wishlist, POST/GET/DELETE /reservations
찜 추가 → 목록 확인 → 찜 해제
시청예약 등록 → 목록 확인 → 예약 취소
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import pytest

from tests.conftest import FIXTURE_SERIES_NM

_TEST_SERIES = FIXTURE_SERIES_NM


@pytest.mark.asyncio
async def test_wishlist_add_and_remove(async_client, tester_token):
    """찜 추가 → 확인 → 해제 사이클."""
    headers = {"Authorization": f"Bearer {tester_token}"}

    # 1. 추가
    resp = await async_client.post(
        "/wishlist",
        json={"series_nm": _TEST_SERIES},
        headers=headers,
    )
    assert resp.status_code in (200, 201, 409)  # 409 = 이미 찜

    # 2. 목록 확인
    resp = await async_client.get("/user/me/wishlist", headers=headers)
    assert resp.status_code == 200
    wishlist = resp.json()["items"]
    series_names = [w.get("series_nm") for w in wishlist]
    assert _TEST_SERIES in series_names

    # 3. 해제
    encoded = quote(_TEST_SERIES, safe="")
    resp = await async_client.delete(f"/wishlist/{encoded}", headers=headers)
    assert resp.status_code in (200, 204)

    # 4. 해제 후 목록 확인
    resp = await async_client.get("/user/me/wishlist", headers=headers)
    assert resp.status_code == 200
    wishlist_after = resp.json()["items"]
    series_after = [w.get("series_nm") for w in wishlist_after]
    assert _TEST_SERIES not in series_after


@pytest.mark.asyncio
async def test_reservation_crud(async_client, tester_token):
    """시청예약 등록 → 목록 확인 → 취소 사이클."""
    headers = {"Authorization": f"Bearer {tester_token}"}
    alert_at = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    # 1. 등록
    resp = await async_client.post(
        "/reservations",
        json={
            "channel": 25,
            "program_name": "제철장터",
            "alert_at": alert_at,
        },
        headers=headers,
    )
    assert resp.status_code in (200, 201)
    reservation_id = resp.json().get("reservation_id")
    assert reservation_id is not None

    # 2. 목록 확인
    resp = await async_client.get("/reservations", headers=headers)
    assert resp.status_code == 200
    reservations = resp.json()["items"]
    ids = [r.get("reservation_id") for r in reservations]
    assert reservation_id in ids

    # 3. 취소
    resp = await async_client.delete(f"/reservations/{reservation_id}", headers=headers)
    assert resp.status_code in (200, 204)

    # 4. 취소 후 목록 확인
    resp = await async_client.get("/reservations", headers=headers)
    assert resp.status_code == 200
    ids_after = [r.get("reservation_id") for r in resp.json()["items"]]
    assert reservation_id not in ids_after
