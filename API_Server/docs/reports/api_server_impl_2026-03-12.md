# API_Server FastAPI 백엔드 구현 리포트

- 작성일: 2026-03-12
- 작성자: 박아름
- 브랜치: API_Server

---

## 배경

VOD 추천 시스템의 서비스 레이어(Phase 4) 첫 번째 구현.
CF_Engine, Vector_Search, Shopping_Ad의 결과를 단일 REST API로 통합하여 Frontend에 제공.

---

## 구현 파일

```
API_Server/
├── app/
│   ├── main.py                        ← FastAPI 앱 진입점, lifespan DB 풀
│   ├── routers/
│   │   ├── auth.py                    ← POST /auth/token
│   │   ├── vod.py                     ← GET /vod/{asset_id}
│   │   ├── recommend.py               ← GET /recommend/{user_id}
│   │   └── search.py                  ← GET /similar/{asset_id}
│   ├── services/
│   │   ├── db.py                      ← asyncpg 커넥션 풀
│   │   ├── vod_service.py             ← public.vod 조회
│   │   ├── recommend_service.py       ← serving.vod_recommendation + fallback
│   │   └── search_service.py          ← VISUAL_SIMILARITY + 장르 fallback
│   └── models/
│       ├── auth.py                    ← TokenRequest, TokenResponse
│       ├── vod.py                     ← VodDetailResponse
│       └── recommend.py               ← RecommendResponse, SimilarVodResponse
├── config/
│   ├── .env.example
│   └── settings.yaml
└── docs/
    └── plans/PLAN_00~05.md
```

---

## 엔드포인트 구현 현황

| 메서드 | 경로 | 상태 | 비고 |
|--------|------|------|------|
| POST | `/auth/token` | ✅ 완료 | JWT HS256, 60분 만료 |
| GET | `/vod/{asset_id}` | ✅ 완료 | public.vod PK 조회 |
| GET | `/recommend/{user_id}` | ✅ 완료 | serving 미적재 시 fallback |
| GET | `/similar/{asset_id}` | ✅ 완료 | Vector_Search 미구현 시 장르 fallback |
| WS | `/ad/popup` | 🔲 예정 | Shopping_Ad 완료 후 PLAN_06 |

---

## 주요 기술 결정

### 1. asyncpg 커넥션 풀 (min=2, max=10)

VPC `max_connections=100` 제한 + 팀원 백그라운드 작업 ~25개 점유로
API 서버 풀을 max=10으로 고정. 수평 확장 시 PgBouncer 도입 필요.

### 2. Fallback 전략

| 엔드포인트 | Primary | Fallback |
|-----------|---------|---------|
| /recommend | serving.vod_recommendation | serving.mv_vod_watch_stats (인기순) |
| /similar | VISUAL_SIMILARITY | 동일 장르 VOD |

serving 스키마 미생성 시에도 예외 없이 응답 반환.

### 3. Windows DSN 조합 대응

Windows `.env`에서 `DATABASE_URL=${DB_HOST}` 형식의 변수 치환이 미지원.
`db.py`에서 `DATABASE_URL` 없을 시 `DB_HOST`, `DB_NAME` 등 개별 변수로 DSN 자동 조합.

### 4. public."user" PK 컬럼

초기 구현에서 `user_id`로 작성했으나 실제 PK는 `sha2_hash`.
`Database_Design/schemas/` 확인 후 수정, DEPENDENCY_MAP.md 동시 업데이트.

---

## 테스트 결과

| 엔드포인트 | HTTP 코드 | 결과 |
|-----------|----------|------|
| POST /auth/token | 200 | JWT 발급 정상 |
| GET /vod/cjc\|I0001179LFO108245001 | 200 | 메타데이터 정상 반환 |
| GET /recommend/{sha2_hash} | 200 | `popular_fallback` 빈배열 (serving 미적재) |
| GET /similar/cjc\|I0001179LFO108245001 | 200 | `genre_fallback` 10건 반환 |

---

## 이슈 및 해결

| 이슈 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError: No module named 'app'` | 루트에서 `uvicorn API_Server.app.main:app` 실행 | `cd API_Server` 후 실행 |
| `asyncpg.ConnectionDoesNotExistError` | Windows에서 `${변수}` 치환 안 됨 | db.py 개별 변수 DSN 조합 추가 |
| `column "user_id" does not exist` | user 테이블 PK가 sha2_hash | DB 스키마 확인 후 수정 |

---

## 다음 단계

- `tests/` pytest 작성 (httpx AsyncClient)
- Shopping_Ad 완료 후 WS `/ad/popup` 구현 (PLAN_06)
- serving 스키마 데이터 적재 시 /recommend 실데이터 검증
