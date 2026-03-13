# PLAN_00: API_Server 마스터 플랜

**브랜치**: API_Server
**작성일**: 2026-03-12
**목표**: FastAPI 백엔드 — CF_Engine·Vector_Search·Shopping_Ad 결과를 단일 REST API로 통합하여 Frontend에 제공

> **범위 주의**: API_Server는 Gold 레이어(serving.*)에서 사전 계산된 결과만 읽어 JSON으로 전달한다.
> 벡터 연산·집계 연산은 수행하지 않는다.

---

## 전체 구조

```
[PLAN_01] 앱 기본 설정
          FastAPI init / CORS / asyncpg 커넥션 풀 / config

[PLAN_02] /vod/{asset_id}
          public.vod 테이블 → VOD 상세 메타데이터 응답

[PLAN_03] /recommend/{user_id}
          serving.vod_recommendation → 개인화 추천 결과 응답

[PLAN_04] /similar/{asset_id}
          serving.vod_recommendation (VISUAL_SIMILARITY) → 유사 콘텐츠 응답

[PLAN_05] /auth/token
          JWT 발급 (POST) / 검증 Depends
```

> `/ad/popup` (WebSocket) — Shopping_Ad 브랜치 완료 후 PLAN_06으로 추가 예정

---

## 단계별 요약

| 단계 | 파일 | 입력 | 출력 |
|------|------|------|------|
| PLAN_01 | `app/main.py`, `app/services/db.py`, `config/settings.yaml` | 환경변수 (.env) | FastAPI 앱 + DB 풀 |
| PLAN_02 | `app/routers/vod.py`, `app/services/vod_service.py`, `app/models/vod.py` | `public.vod` | `VodDetailResponse` JSON |
| PLAN_03 | `app/routers/recommend.py`, `app/services/recommend_service.py`, `app/models/recommend.py` | `serving.vod_recommendation` | `RecommendResponse` JSON |
| PLAN_04 | `app/routers/search.py`, `app/services/search_service.py` | `serving.vod_recommendation` | `SimilarVodResponse` JSON |
| PLAN_05 | `app/routers/auth.py`, `app/models/auth.py` | `public."user"` | JWT access_token |

---

## 사전 조건

| 조건 | 확인 방법 | 상태 |
|------|-----------|------|
| `public.vod` 166,159건 적재 완료 | `SELECT COUNT(*) FROM vod;` | ✅ 완료 |
| `public."user"` 적재 완료 | `SELECT COUNT(*) FROM "user";` | ✅ 완료 |
| `serving.vod_recommendation` 테이블 생성 | `\dt serving.*` | 🔲 CF_Engine/Vector_Search 완료 후 |
| `serving.mv_vod_watch_stats` MV 생성 | `\dm serving.*` | 🔲 Database_Design 배포 후 |
| `.env` 파일 수령 (DB 접속 정보) | 조장(dhwang0803)에게 문의 | ✅ 기존 .env 재사용 |

---

## 파일 구조

```
API_Server/
├── app/
│   ├── main.py                    ← FastAPI 진입점, 라우터 등록, 커넥션 풀
│   ├── routers/
│   │   ├── vod.py                 ← PLAN_02: GET /vod/{asset_id}
│   │   ├── recommend.py           ← PLAN_03: GET /recommend/{user_id}
│   │   ├── search.py              ← PLAN_04: GET /similar/{asset_id}
│   │   └── auth.py                ← PLAN_05: POST /auth/token
│   ├── services/
│   │   ├── db.py                  ← asyncpg 풀 생성/종료 (PLAN_01)
│   │   ├── vod_service.py         ← VOD 조회 로직 (PLAN_02)
│   │   ├── recommend_service.py   ← 추천 조회 로직 (PLAN_03)
│   │   └── search_service.py      ← 유사 콘텐츠 조회 로직 (PLAN_04)
│   └── models/
│       ├── vod.py                 ← VodDetailResponse Pydantic 스키마
│       ├── recommend.py           ← RecommendResponse Pydantic 스키마
│       └── auth.py                ← TokenRequest / TokenResponse Pydantic 스키마
├── tests/
│   ├── test_vod.py
│   ├── test_recommend.py
│   ├── test_search.py
│   └── test_auth.py
├── config/
│   └── settings.yaml              ← 포트, CORS 허용 오리진, JWT 만료시간 등
└── docs/
    └── plans/
        ├── PLAN_00_MASTER.md      ← 이 파일
        ├── PLAN_01_SETUP.md
        ├── PLAN_02_VOD_ROUTER.md
        ├── PLAN_03_RECOMMEND_ROUTER.md
        ├── PLAN_04_SEARCH_ROUTER.md
        └── PLAN_05_AUTH_ROUTER.md
```

---

## 엔드포인트 설계

| 메서드 | 경로 | 설명 | 소스 테이블 | 인증 |
|--------|------|------|-------------|------|
| GET | `/vod/{asset_id}` | VOD 상세 메타데이터 | `public.vod` | 불필요 |
| GET | `/recommend/{user_id}` | 개인화 추천 목록 | `serving.vod_recommendation` | JWT 필요 |
| GET | `/similar/{asset_id}` | 유사 콘텐츠 목록 | `serving.vod_recommendation` | 불필요 |
| POST | `/auth/token` | JWT 발급 | `public."user"` | 불필요 |
| WS | `/ad/popup` | 실시간 광고 트리거 | Shopping_Ad | JWT 필요 (예정) |

---

## DB 커넥션 풀 설계

> ⚠️ VPC `max_connections = 100`. 팀원 백그라운드 작업 ~25개 점유 중.

```python
# app/services/db.py
asyncpg.create_pool(
    dsn=os.getenv("DATABASE_URL"),
    min_size=2,
    max_size=10,   # 100 - 25(팀원) - 5(예약) = 여유 70개 중 보수적 설정
)
```

---

## 실행 방법

```bash
# 환경변수 로드
set -a && source .env && set +a

# 개발 서버
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 프로덕션
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## 진행 체크리스트

- [ ] PLAN_01: `app/main.py` + `app/services/db.py` + `config/settings.yaml`
- [ ] PLAN_02: `/vod/{asset_id}` 라우터 + 서비스 + Pydantic 모델
- [ ] PLAN_03: `/recommend/{user_id}` 라우터 + 서비스 + Pydantic 모델
- [ ] PLAN_04: `/similar/{asset_id}` 라우터 + 서비스
- [ ] PLAN_05: `/auth/token` 라우터 + JWT 유틸
- [ ] pytest 전체 통과
- [ ] VPC 환경에서 파이럿 테스트

---

**다음**: PLAN_01_SETUP.md
