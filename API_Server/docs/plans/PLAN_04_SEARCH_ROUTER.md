# PLAN_04: 유사 콘텐츠 엔드포인트

**목표**: `GET /similar/{asset_id}` — 기준 VOD와 유사한 콘텐츠 목록을 반환

> ⚠️ **사전 조건**: `serving.vod_recommendation`의 `recommendation_type = 'VISUAL_SIMILARITY'` 행은
> Vector_Search 브랜치 완료 후 적재된다.
> 그 전까지는 동일 장르 VOD를 fallback으로 반환한다.

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | Path param `asset_id` (VARCHAR(64)), Query param `limit` (default 10) |
| **출력** | `SimilarVodResponse` JSON |
| **소스 테이블** | `serving.vod_recommendation` (VISUAL_SIMILARITY) / `public.vod` (fallback) |
| **인증** | 불필요 |

---

## DB 쿼리 (Primary)

```sql
-- Vector_Search가 적재한 VISUAL_SIMILARITY 결과
SELECT
    r.vod_id_fk  AS asset_id,
    r.rank,
    r.score,
    v.asset_nm   AS title,
    v.genre,
    v.poster_url
FROM serving.vod_recommendation r
JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
WHERE r.user_id_fk = $1               -- asset_id를 user_id_fk 자리에 저장하는 설계
  AND r.recommendation_type = 'VISUAL_SIMILARITY'
ORDER BY r.rank
LIMIT $2;
```

> ⚠️ `serving.vod_recommendation` 스키마 상 `user_id_fk` 컬럼을 기준 VOD asset_id로 사용하는지
> 또는 별도 컬럼이 필요한지 **Vector_Search 브랜치와 협의 필요**.
> 협의 결과에 따라 이 쿼리를 수정한다.

## DB 쿼리 (Fallback — 동일 장르)

```sql
SELECT
    v.full_asset_id  AS asset_id,
    v.asset_nm       AS title,
    v.genre,
    v.poster_url
FROM public.vod v
WHERE v.genre = (SELECT genre FROM public.vod WHERE full_asset_id = $1)
  AND v.full_asset_id <> $1
LIMIT $2;
```

---

## Pydantic 모델: `app/models/recommend.py` (공유)

```python
class SimilarVodItem(BaseModel):
    asset_id: str
    title: str
    genre: str | None
    poster_url: str | None
    score: float | None
    rank: int | None

class SimilarVodResponse(BaseModel):
    base_asset_id: str
    items: list[SimilarVodItem]
    total: int
    source: str   # 'vector_similarity' | 'genre_fallback'
```

---

## 서비스: `app/services/search_service.py`

```python
from app.services.db import get_pool

async def get_similar_vods(asset_id: str, limit: int = 10) -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT r.vod_id_fk AS asset_id, r.rank, r.score,
                   v.asset_nm AS title, v.genre, v.poster_url
            FROM serving.vod_recommendation r
            JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
            WHERE r.user_id_fk = $1
              AND r.recommendation_type = 'VISUAL_SIMILARITY'
            ORDER BY r.rank LIMIT $2
            """,
            asset_id, limit,
        )

    if rows:
        return {"items": [dict(r) for r in rows], "source": "vector_similarity"}

    # Fallback: 동일 장르
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT v.full_asset_id AS asset_id, v.asset_nm AS title,
                   v.genre, v.poster_url,
                   NULL AS score,
                   ROW_NUMBER() OVER () AS rank
            FROM public.vod v
            WHERE v.genre = (SELECT genre FROM public.vod WHERE full_asset_id = $1)
              AND v.full_asset_id <> $1
            LIMIT $2
            """,
            asset_id, limit,
        )
    return {"items": [dict(r) for r in rows], "source": "genre_fallback"}
```

---

## 라우터: `app/routers/search.py`

```python
from fastapi import APIRouter, HTTPException, Query
from app.services.search_service import get_similar_vods
from app.models.recommend import SimilarVodResponse

router = APIRouter()

@router.get("/{asset_id}", response_model=SimilarVodResponse)
async def similar_vods(
    asset_id: str,
    limit: int = Query(default=10, ge=1, le=50),
):
    result = await get_similar_vods(asset_id, limit)
    if not result["items"]:
        raise HTTPException(status_code=404, detail="No similar VOD found")
    return SimilarVodResponse(
        base_asset_id=asset_id,
        items=result["items"],
        total=len(result["items"]),
        source=result["source"],
    )
```

---

## 예외 처리

| 상황 | HTTP 코드 | 처리 |
|------|-----------|------|
| 기준 VOD 존재하지 않음 | 404 | `No similar VOD found` |
| 동일 장르 VOD 없음 | 404 | `No similar VOD found` |
| `serving.vod_recommendation` 미생성 | — | fallback으로 자동 전환 |

---

## 검증

```bash
curl http://localhost:8000/similar/{asset_id}?limit=5
```

---

## Vector_Search 브랜치 협의 사항

- `serving.vod_recommendation`에서 유사 콘텐츠 저장 방식 확인 필요
- `recommendation_type = 'VISUAL_SIMILARITY'` 컬럼값 통일
- 기준 VOD asset_id 저장 컬럼 확인 (현재는 `user_id_fk` 컬럼 임시 사용 가정)

---

**다음**: PLAN_05_AUTH_ROUTER.md
