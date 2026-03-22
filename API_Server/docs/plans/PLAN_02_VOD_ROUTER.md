# PLAN_02: VOD 상세 엔드포인트

**목표**: `GET /vod/{asset_id}` — `public.vod` 테이블에서 VOD 상세 메타데이터를 조회하여 JSON으로 반환

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | Path param `asset_id` (= `full_asset_id`, VARCHAR(64)) |
| **출력** | `VodDetailResponse` JSON |
| **소스 테이블** | `public.vod` |

---

## DB 쿼리

```sql
SELECT
    full_asset_id,
    asset_nm,
    genre,
    ct_cl,
    director,
    cast_lead,
    cast_guest,
    smry,
    rating,
    release_date,
    poster_url,
    asset_prod
FROM public.vod
WHERE full_asset_id = $1;
```

> `full_asset_id` 기준 PK 조회 → Index Scan, 응답 목표 < 10ms

---

## Pydantic 모델: `app/models/vod.py`

```python
from pydantic import BaseModel
from datetime import date

class VodDetailResponse(BaseModel):
    asset_id: str
    title: str
    genre: str | None
    category: str | None
    director: str | None
    cast_lead: str | None
    cast_guest: str | None
    summary: str | None
    rating: str | None
    release_year: int | None    # date → 연도만 반환 (2026-03-20 결정)
    poster_url: str | None
    is_free: bool               # asset_prod == 'FOD' (2026-03-20 추가)
```

---

## 서비스: `app/services/vod_service.py`

```python
from app.services.db import get_pool

async def get_vod_detail(asset_id: str) -> dict | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT full_asset_id, asset_nm, genre, ct_cl,
                   director, cast_lead, cast_guest, smry,
                   rating, release_date, poster_url
            FROM public.vod
            WHERE full_asset_id = $1
            """,
            asset_id,
        )
    return dict(row) if row else None
```

---

## 라우터: `app/routers/vod.py`

```python
from fastapi import APIRouter, HTTPException
from app.services.vod_service import get_vod_detail
from app.models.vod import VodDetailResponse

router = APIRouter()

@router.get("/{asset_id}", response_model=VodDetailResponse)
async def vod_detail(asset_id: str):
    vod = await get_vod_detail(asset_id)
    if vod is None:
        raise HTTPException(status_code=404, detail="VOD not found")
    return VodDetailResponse(
        asset_id=vod["full_asset_id"],
        title=vod["asset_nm"],
        genre=vod["genre"],
        category=vod["ct_cl"],
        director=vod["director"],
        cast_lead=vod["cast_lead"],
        cast_guest=vod["cast_guest"],
        summary=vod["smry"],
        rating=vod["rating"],
        release_year=vod["release_date"].year if vod["release_date"] else None,
        poster_url=vod["poster_url"],
        is_free=vod.get("asset_prod") == "FOD",
    )
```

---

## 예외 처리

| 상황 | HTTP 코드 | 처리 |
|------|-----------|------|
| `asset_id` 미존재 | 404 | `VOD not found` |
| DB 연결 오류 | 503 | 풀 타임아웃 → 자동 503 |

---

## 검증

```bash
# 정상 조회
curl http://localhost:8000/vod/{실제_asset_id}

# 없는 ID
curl http://localhost:8000/vod/FAKE_ID
# 기대: {"detail": "VOD not found"}
```

```python
# pytest: tests/test_vod.py
from httpx import AsyncClient

async def test_vod_detail_found(client: AsyncClient):
    response = await client.get("/vod/{실제_asset_id}")
    assert response.status_code == 200
    data = response.json()
    assert "title" in data

async def test_vod_detail_not_found(client: AsyncClient):
    response = await client.get("/vod/FAKE_ID_DOES_NOT_EXIST")
    assert response.status_code == 404
```

---

**다음**: PLAN_03_RECOMMEND_ROUTER.md
