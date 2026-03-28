"""
pytest 공용 픽스처

- async_client: 실제 DB 연결 FastAPI TestClient (httpx.AsyncClient)
- tester_token: 테스터 12명 sha2_hash → JWT 토큰
- TESTERS: 페르소나별 sha2_hash 상수
"""

import hashlib
import os

import pytest
import pytest_asyncio
from dotenv import load_dotenv
from httpx import ASGITransport, AsyncClient

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

# 테스트용 JWT 시크릿 (환경변수 미설정 시 fallback)
if not os.getenv("JWT_SECRET_KEY"):
    os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-pytest-only"

# ── 테스터 상수 ──────────────────────────────────────────────────────────────
_PREFIX = "test_"

TESTERS: dict[str, str] = {
    label: hashlib.sha256((_PREFIX + label).encode()).hexdigest()
    for label in [
        "C0_저관여_50대",
        "C0_저관여_60대",
        "C1_충성_50대",
        "C1_충성_40대",
        "C1_충성_30대",
        "C1_충성_60대",
        "C2_헤비_50대",
        "C2_헤비_40대",
        "C2_헤비_30대",
        "C3_키즈_40대",
        "C3_키즈_30대",
        "C3_키즈_60대",
    ]
}

# 테스트에 쓸 고정 픽스처 값 (DB에 존재 확인된 실제 값)
FIXTURE_USER_ID   = TESTERS["C1_충성_40대"]   # watch_history 50건 — 충성 유저
FIXTURE_VOD_ID    = "cjc|M4442212LSGJ77541101"  # 쌈 마이웨이 02회
FIXTURE_SERIES_NM = "쌈 마이웨이"
FIXTURE_SIMILAR_VOD_ID = "cjc|M4710228LSGH90526801"  # CONTENT_BASED 추천 존재


@pytest_asyncio.fixture(scope="session")
async def async_client():
    """lifespan 포함 실제 DB 연결 TestClient."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from app.main import app
    from app.services.db import create_pool, close_pool

    # lifespan 대신 pool을 테스트용으로 직접 초기화
    await create_pool()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            yield client
    finally:
        await close_pool()


@pytest_asyncio.fixture(scope="session")
async def tester_token(async_client):
    """C1_충성_40대 테스터 JWT 토큰 (인증 필요 엔드포인트용)."""
    resp = await async_client.post("/auth/token", json={"user_id": FIXTURE_USER_ID})
    assert resp.status_code == 200, f"토큰 발급 실패: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture
def auth_headers(tester_token):
    return {"Authorization": f"Bearer {tester_token}"}
