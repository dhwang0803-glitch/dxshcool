# PLAN_01: 앱 기본 설정

**목표**: FastAPI 앱 초기화, asyncpg 커넥션 풀, CORS 설정, config 로딩

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | `.env` (DB 접속 정보, JWT 시크릿) |
| **출력** | 실행 가능한 FastAPI 앱 (`uvicorn app.main:app`) |

---

## 구현 파일: `app/services/db.py`

```python
import asyncpg
import os

_pool: asyncpg.Pool | None = None

async def create_pool() -> asyncpg.Pool:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn=os.getenv("DATABASE_URL"),   # 기본값 없음 — 보안 규칙
        min_size=2,
        max_size=10,
    )
    return _pool

async def close_pool():
    global _pool
    if _pool:
        await _pool.close()

async def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized")
    return _pool
```

> `DATABASE_URL` 형식: `postgresql://USER:PASS@HOST:PORT/DBNAME`
> `.env`에서 `DATABASE_URL=postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME` 로 조합

---

## 구현 파일: `app/main.py`

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.services.db import create_pool, close_pool
from app.routers import vod, recommend, search, auth

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    yield
    await close_pool()

app = FastAPI(title="VOD Recommendation API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # config에서 환경별로 제한
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vod.router, prefix="/vod", tags=["vod"])
app.include_router(recommend.router, prefix="/recommend", tags=["recommend"])
app.include_router(search.router, prefix="/similar", tags=["search"])
app.include_router(auth.router, prefix="/auth", tags=["auth"])
```

---

## 구현 파일: `config/settings.yaml`

```yaml
app:
  host: "0.0.0.0"
  port: 8000
  workers: 2

cors:
  allow_origins:
    - "http://localhost:3000"   # Frontend 개발 서버

jwt:
  algorithm: "HS256"
  expire_minutes: 60
```

---

## 환경변수 목록 (`.env.example`)

```dotenv
# DB 접속 (조장에게 수령)
DB_HOST=
DB_PORT=5432
DB_NAME=
DB_USER=
DB_PASSWORD=
DATABASE_URL=postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}

# JWT
JWT_SECRET_KEY=
```

> `.env` 파일은 Git 커밋 금지. `config/` 폴더에 `.env.example`만 커밋.

---

## 검증

```bash
# 서버 기동 확인
uvicorn app.main:app --reload --port 8000

# 헬스 체크
curl http://localhost:8000/docs
```

---

## 예외 처리

| 상황 | 처리 |
|------|------|
| `DATABASE_URL` 환경변수 없음 | 앱 기동 시 즉시 RuntimeError — 운영 환경 배포 전 필수 확인 |
| DB 접속 실패 | `asyncpg.InvalidCatalogNameError` → 로그 출력 후 프로세스 종료 |
| 커넥션 풀 고갈 | asyncpg 타임아웃 → 503 Service Unavailable 응답 |

---

**다음**: PLAN_02_VOD_ROUTER.md
