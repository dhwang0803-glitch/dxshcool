import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from app.models.auth import TokenRequest, TokenResponse
from app.services.db import get_pool

router = APIRouter()
security = HTTPBearer()

ALGORITHM = "HS256"


def _secret() -> str:
    key = os.getenv("JWT_SECRET_KEY")
    if not key:
        raise RuntimeError("JWT_SECRET_KEY env var is not set.")
    return key


def create_access_token(user_id: str) -> str:
    """셋톱박스 자동 로그인 — 만료 없는 토큰 발급."""
    payload = {"sub": user_id}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> str:
    try:
        payload = jwt.decode(credentials.credentials, _secret(), algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user_id
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/token", response_model=TokenResponse)
async def issue_token(request: TokenRequest):
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            'SELECT 1 FROM public."user" WHERE sha2_hash = $1',
            request.user_id,
        )
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return TokenResponse(access_token=create_access_token(request.user_id))
