# PLAN_03: 개인화 추천 엔드포인트

**목표**: `GET /recommend/{user_id}` — `serving.vod_recommendation`에서 사전 계산된 추천 결과를 조회하여 반환

> ⚠️ **사전 조건**: `serving.vod_recommendation` 테이블은 Hybrid_Layer가 CF_Engine + Vector_Search 결과를
> 리랭킹한 후 `recommendation_type = 'HYBRID'`로 적재한다.
> 그 전까지는 `serving.mv_vod_watch_stats` 인기 콘텐츠 fallback으로 응답한다.
>
> **UNIQUE 제약 (2026-03-20 변경)**: `UNIQUE(user_id_fk, vod_id_fk, recommendation_type)` — CF/Vector/Hybrid 타입별 독립 저장.

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | Path param `user_id` (VARCHAR(64)), Query param `limit` (default 10) |
| **출력** | `RecommendResponse` JSON |
| **소스 테이블** | `serving.vod_recommendation` (primary) / `serving.mv_vod_watch_stats` (fallback) |
| **인증** | JWT Bearer 필요 |

---

## DB 쿼리 (Primary)

```sql
-- serving.vod_recommendation 에서 Hybrid 개인화 추천
SELECT
    r.vod_id_fk      AS asset_id,
    r.rank,
    r.score,
    r.recommendation_type,
    v.asset_nm       AS title,
    v.genre,
    v.poster_url
FROM serving.vod_recommendation r
JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
WHERE r.user_id_fk = $1
  AND r.recommendation_type = 'HYBRID'
ORDER BY r.rank
LIMIT $2;
```

## DB 쿼리 (Fallback — recommendation 없을 때)

```sql
-- serving.mv_vod_watch_stats 인기 콘텐츠 기반
SELECT
    s.vod_id_fk      AS asset_id,
    v.asset_nm       AS title,
    v.genre,
    v.poster_url,
    s.total_watch_count
FROM serving.mv_vod_watch_stats s
JOIN public.vod v ON s.vod_id_fk = v.full_asset_id
ORDER BY s.total_watch_count DESC
LIMIT $1;
```

> `mv_vod_watch_stats`는 MV이므로 응답 < 10ms 목표 (phase3B 성능 기준 준수)

---

## Pydantic 모델: `app/models/recommend.py`

```python
from pydantic import BaseModel

class RecommendItem(BaseModel):
    asset_id: str
    title: str
    genre: str | None
    poster_url: str | None
    score: float | None
    rank: int | None
    recommendation_type: str | None   # 'HYBRID' | 'COLLABORATIVE' | 'VISUAL_SIMILARITY' | 'CONTENT_BASED' | 'POPULAR'

class RecommendResponse(BaseModel):
    user_id: str
    items: list[RecommendItem]
    total: int
    source: str   # 'personalized' | 'popular_fallback'
```

---

## 서비스: `app/services/recommend_service.py`

```python
from app.services.db import get_pool

async def get_recommendations(user_id: str, limit: int = 10) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT r.vod_id_fk AS asset_id, r.rank, r.score,
                   r.recommendation_type, v.asset_nm AS title,
                   v.genre, v.poster_url
            FROM serving.vod_recommendation r
            JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
            WHERE r.user_id_fk = $1
            ORDER BY r.rank LIMIT $2
            """,
            user_id, limit,
        )

    if rows:
        return {"items": [dict(r) for r in rows], "source": "personalized"}

    # Fallback: 인기 콘텐츠
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT s.vod_id_fk AS asset_id, v.asset_nm AS title,
                   v.genre, v.poster_url, NULL AS score,
                   ROW_NUMBER() OVER (ORDER BY s.total_watch_count DESC) AS rank,
                   'POPULAR' AS recommendation_type
            FROM serving.mv_vod_watch_stats s
            JOIN public.vod v ON s.vod_id_fk = v.full_asset_id
            ORDER BY s.total_watch_count DESC LIMIT $1
            """,
            limit,
        )
    return {"items": [dict(r) for r in rows], "source": "popular_fallback"}
```

---

## 라우터: `app/routers/recommend.py`

```python
from fastapi import APIRouter, Depends, Query
from app.services.recommend_service import get_recommendations
from app.models.recommend import RecommendResponse
from app.routers.auth import get_current_user

router = APIRouter()

@router.get("/{user_id}", response_model=RecommendResponse)
async def recommend(
    user_id: str,
    limit: int = Query(default=10, ge=1, le=50),
    current_user: str = Depends(get_current_user),
):
    result = await get_recommendations(user_id, limit)
    return RecommendResponse(
        user_id=user_id,
        items=result["items"],
        total=len(result["items"]),
        source=result["source"],
    )
```

---

## 예외 처리

| 상황 | HTTP 코드 | 처리 |
|------|-----------|------|
| JWT 없음 / 만료 | 401 | `get_current_user` Depends에서 처리 |
| `user_id` 존재하지 않음 | 200 | fallback 인기 콘텐츠 반환 (에러 아님) |
| `serving.vod_recommendation` 테이블 미생성 | 500 | `UndefinedTableError` → 서비스 레이어에서 fallback으로 전환 |
| `limit` 범위 초과 (>50) | 422 | FastAPI Query 유효성 검사 자동 처리 |

---

## 검증

```bash
# 인증 토큰 발급 후 추천 조회
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token \
  -H "Content-Type: application/json" \
  -d '{"user_id":"test_user"}' | jq -r '.access_token')

curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/recommend/{user_id}?limit=5
```

```sql
-- 추천 결과 존재 확인 (CF_Engine 완료 후)
SELECT COUNT(*) FROM serving.vod_recommendation WHERE user_id_fk = '{user_id}';
```

---

**다음**: PLAN_04_SEARCH_ROUTER.md
