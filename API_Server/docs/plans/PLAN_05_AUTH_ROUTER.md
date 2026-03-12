# PLAN_05: JWT 인증 엔드포인트

**목표**: `POST /auth/token` — user_id 기반 JWT 발급 / Bearer 토큰 검증 Depends 제공

> **범위 주의**: 이 프로젝트는 실제 인증 서버가 아니다.
> 팀 내부 데모·테스트용으로 user_id가 `public."user"` 테이블에 존재하는지만 확인 후 JWT를 발급한다.
> 패스워드 해싱, OAuth 등은 이 브랜치 범위 밖이다.

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | `TokenRequest` JSON (`user_id`) |
| **출력** | `TokenResponse` JSON (`access_token`, `token_type`) |
| **소스 테이블** | `public."user"` |

---

## DB 쿼리

```sql
-- user_id 존재 여부 확인
SELECT 1 FROM public."user" WHERE user_id = $1 LIMIT 1;
```

> `public."user"` 테이블의 PK 컬럼명은 Database_Design 브랜치 스키마 기준.
> 실제 컬럼명이 다를 경우 `Database_Design/schemas/` SQL 파일 확인 후 수정.

---

## Pydantic 모델: `app/models/auth.py`

```python
from pydantic import BaseModel

class TokenRequest(BaseModel):
    user_id: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
```

---

## JWT 유틸 (라우터 내 또는 `app/services/` 분리)

```python
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

SECRET_KEY = os.getenv("JWT_SECRET_KEY")   # 기본값 없음 — 보안 규칙
ALGORITHM = "HS256"
EXPIRE_MINUTES = 60

security = HTTPBearer()

def create_access_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(minutes=EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
```

---

## 라우터: `app/routers/auth.py`

```python
from fastapi import APIRouter, HTTPException
from app.services.db import get_pool
from app.models.auth import TokenRequest, TokenResponse
from app.routers.auth import create_access_token   # 같은 파일 내 정의

router = APIRouter()

@router.post("/token", response_model=TokenResponse)
async def issue_token(request: TokenRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT 1 FROM public."user" WHERE user_id = $1',
            request.user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    token = create_access_token(request.user_id)
    return TokenResponse(access_token=token)
```

---

## 예외 처리

| 상황 | HTTP 코드 | 처리 |
|------|-----------|------|
| `user_id` 미존재 | 404 | `User not found` |
| `JWT_SECRET_KEY` 환경변수 없음 | 500 | 앱 기동 시 환경변수 체크로 방지 |
| 만료된 토큰 | 401 | `Invalid or expired token` |
| 변조된 토큰 | 401 | `Invalid or expired token` |

---

## 검증

```bash
# 토큰 발급
curl -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id": "실제_user_id"}'
# 기대: {"access_token": "eyJ...", "token_type": "bearer"}

# 없는 유저
curl -X POST http://localhost:8000/auth/token \
  -d '{"user_id": "FAKE_USER"}'
# 기대: 404

# 만료 토큰으로 추천 요청
curl -H "Authorization: Bearer 만료된토큰" http://localhost:8000/recommend/{user_id}
# 기대: 401
```

```python
# pytest: tests/test_auth.py
async def test_issue_token_success(client):
    response = await client.post("/auth/token", json={"user_id": "실제_user_id"})
    assert response.status_code == 200
    assert "access_token" in response.json()

async def test_issue_token_user_not_found(client):
    response = await client.post("/auth/token", json={"user_id": "FAKE_USER"})
    assert response.status_code == 404
```

---

**완료**: 전체 파이프라인 체크리스트는 PLAN_00_MASTER.md 참고
