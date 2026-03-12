import asyncpg
import os

_pool: asyncpg.Pool | None = None


def _get_dsn() -> str:
    # DATABASE_URL 이 직접 설정된 경우 우선 사용
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # 없으면 개별 변수로 조합 (Windows .env 변수 치환 미지원 대응)
    host = os.getenv("DB_HOST")
    port = os.getenv("DB_PORT", "5432")
    name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD")
    if not all([host, name, user, password]):
        raise RuntimeError("DB 접속 정보 환경변수가 설정되지 않았습니다. (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD)")
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"


async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=_get_dsn(),
        min_size=2,
        max_size=10,
    )
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized. Check DATABASE_URL env var.")
    return _pool
