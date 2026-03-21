# API_Server — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**FastAPI 백엔드** — CF_Engine, Vector_Search, Shopping_Ad의 결과를
단일 REST API로 통합하여 Frontend에 제공한다.

## 파일 위치 규칙 (MANDATORY)

```
API_Server/
├── app/
│   ├── routers/    ← 엔드포인트별 라우터 (직접 실행 X)
│   ├── services/   ← 비즈니스 로직 (직접 실행 X)
│   ├── models/     ← Pydantic 요청/응답 스키마 (직접 실행 X)
│   └── main.py     ← FastAPI 앱 진입점
├── tests/          ← pytest (httpx TestClient)
└── config/         ← 환경별 설정 yaml
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 라우터 (`recommend.py`, `similar.py` 등) | `app/routers/` |
| 비즈니스 로직 (DB 쿼리, 결과 조합) | `app/services/` |
| Pydantic 스키마 (`RecommendResponse` 등) | `app/models/` |
| FastAPI 앱 (`app = FastAPI()`) | `app/main.py` |
| pytest | `tests/` |
| 환경 설정 | `config/` |

**`API_Server/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import asyncpg             # DB 연결 (asyncpg 커넥션 풀)
from jose import jwt       # JWT 인증 (셋톱박스 자동 로그인, 만료 없음)
import uvicorn
```

## 엔드포인트 설계

| 메서드 | 경로 | 설명 | 소스 |
|--------|------|------|------|
| GET | `/recommend/{user_id}` | 개인화 추천 | Hybrid_Layer (`recommendation_type = 'HYBRID'`) |
| GET | `/similar/{asset_id}` | 유사 콘텐츠 | Vector_Search (`source_vod_id` + `recommendation_type = 'CONTENT_BASED'`) |
| WS | `/ad/popup` | 실시간 광고 팝업 (WebSocket) | Shopping_Ad |
| GET | `/vod/{asset_id}` | VOD 상세 메타데이터 (+is_free, release_year) | DB |
| POST | `/auth/token` | JWT 발급 (셋톱박스 자동 로그인, 만료 없음) | 자체 |
| GET | `/home/banner` | 히어로 배너 top 5 | hybrid_recommendation / popular |
| GET | `/home/sections` | CT_CL별 인기 20선 | popular_recommendation |
| GET | `/series/{id}/episodes` | 에피소드 목록 (중복 제거) | vod |
| GET | `/series/{id}/progress` | 시청 진행 현황 | episode_progress |
| POST | `/series/{id}/episodes/{id}/progress` | 진행률 heartbeat (인메모리 버퍼 → 60초 batch flush) | episode_progress |
| GET | `/series/{id}/purchase-check` | 구매 여부 확인 | purchase_history |
| GET | `/series/{id}/purchase-options` | 구매 옵션 (FOD 무료 분기) | vod |
| GET | `/user/me/watching` | 시청 중 콘텐츠 | episode_progress |
| GET | `/user/me/profile` | 프로필 (user_name + point_balance) | user + point_history |
| GET | `/user/me/points` | 포인트 잔액 + 내역 | point_history |
| GET | `/user/me/history` | 시청 내역 | episode_progress |
| GET | `/user/me/purchases` | 구매 내역 | purchase_history |
| GET | `/user/me/wishlist` | 찜 목록 | wishlist |
| POST | `/purchases` | 포인트 구매 트랜잭션 | purchase/point_history |
| POST | `/wishlist` | 찜 추가 | wishlist |
| DELETE | `/wishlist/{series_nm}` | 찜 해제 | wishlist |
| POST | `/reservations` | 시청예약 등록 | watch_reservation |
| GET | `/reservations` | 시청예약 목록 (미알림) | watch_reservation |
| DELETE | `/reservations/{id}` | 시청예약 취소 | watch_reservation |
| GET | `/home/sections/{user_id}` | 개인화 섹션 (장르 시청 비중 + 미시청 도전) | watch_history + popular_recommendation |
| GET | `/user/me/notifications` | 알림 목록 (최신순) | notifications |
| PATCH | `/user/me/notifications/{id}/read` | 알림 읽음 처리 | notifications |
| POST | `/user/me/notifications/read-all` | 전체 읽음 처리 | notifications |
| DELETE | `/user/me/notifications/{id}` | 알림 삭제 | notifications |
| GET | `/vod/search?q={query}` | GNB 통합 검색 (제목/출연진/감독/장르, 최대 8건) | vod (pg_trgm) |

## 실행

```bash
# 개발 서버
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id` | VARCHAR(64) | `/vod/{asset_id}` PK 조회 |
| `public.vod` | `asset_nm`, `genre`, `ct_cl` | VARCHAR | VOD 상세 응답 |
| `public.vod` | `director`, `cast_lead`, `cast_guest` | VARCHAR/TEXT | VOD 상세 응답 |
| `public.vod` | `smry`, `rating`, `release_date`, `poster_url`, `asset_prod` | TEXT/VARCHAR/DATE/TEXT/VARCHAR | VOD 상세 응답. `release_date` → `release_year`(연도 int) 변환. `asset_prod='FOD'` → `is_free=true` |
| `public."user"` | `sha2_hash` | VARCHAR | 사용자 존재 여부 확인 (PK) |
| `public."user"` | `point_balance` | INT | 포인트 잔액 O(1) 조회 (DB 트리거가 point_history INSERT 시 자동 갱신) |
| `public.episode_progress` | `user_id_fk`, `vod_id_fk`, `series_nm`, `completion_rate`, `watched_at` | VARCHAR/VARCHAR/VARCHAR/SMALLINT/TIMESTAMPTZ | 시청 진행률 조회 (시청중/시청내역) |
| `public.purchase_history` | `user_id_fk`, `series_nm`, `purchased_at`, `expires_at` | VARCHAR/VARCHAR/TIMESTAMPTZ/TIMESTAMPTZ | 구매 내역·만료 확인 |
| `public.point_history` | `user_id_fk`, `amount`, `reason`, `created_at` | VARCHAR/INT/VARCHAR/TIMESTAMPTZ | 포인트 내역 조회 |
| `public.wishlist` | `user_id_fk`, `series_nm` | VARCHAR/VARCHAR | 찜 목록 조회 |
| `public.watch_reservation` | `reservation_id`, `user_id_fk`, `channel`, `program_name`, `alert_at`, `notified` | SERIAL/VARCHAR/INT/VARCHAR/TIMESTAMPTZ/BOOLEAN | 시청예약 조회·알림 체크 (30초 주기) |
| `serving.vod_recommendation` | `user_id_fk`, `source_vod_id`, `vod_id_fk`, `rank`, `score`, `recommendation_type`, `expires_at` | VARCHAR/REAL/INT/VARCHAR/TIMESTAMPTZ | `/recommend` (user_id_fk 기준) + `/similar` (source_vod_id 기준). TTL 필터 적용 |
| `serving.mv_vod_watch_stats` | `vod_id_fk`, `total_watch_count` | VARCHAR/INT | /recommend fallback (인기순) |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.episode_progress` | `user_id_fk`, `vod_id_fk`, `series_nm`, `completion_rate`, `watched_at` | VARCHAR/VARCHAR/VARCHAR/SMALLINT/TIMESTAMPTZ | 인메모리 버퍼 → 60초 batch UPSERT. `ON CONFLICT (user_id_fk, vod_id_fk) DO UPDATE` |
| `public.purchase_history` | `user_id_fk`, `series_nm`, `points_used`, `purchased_at`, `expires_at` | VARCHAR/VARCHAR/INT/TIMESTAMPTZ/TIMESTAMPTZ | 트랜잭션 INSERT. 중복 구매 시 무시 |
| `public.point_history` | `user_id_fk`, `amount`, `reason` | VARCHAR/INT/VARCHAR | 트랜잭션 INSERT. DB 트리거가 `user.point_balance` 자동 갱신 + `NOTIFY user_activity` |
| `public.wishlist` | `user_id_fk`, `series_nm` | VARCHAR/VARCHAR | INSERT/DELETE. DB 트리거 `NOTIFY user_activity` |
| `public.watch_reservation` | `user_id_fk`, `channel`, `program_name`, `alert_at` | VARCHAR/INT/VARCHAR/TIMESTAMPTZ | INSERT/DELETE. `notified` 플래그 UPDATE (알림 전송 후) |
| `Frontend` | — | — | REST JSON 응답 / WebSocket (광고 팝업 + 시청예약 알림 + 마이페이지 실시간 갱신) |

> API 서버는 Gold 레이어(serving.*)에서 추천 결과를 읽고, public 스키마에 사용자 활동을 기록한다.
> 벡터 연산·집계는 수행하지 않는다. 실시간 갱신은 PG LISTEN/NOTIFY + 인메모리 버퍼(방안 A)로 처리한다.

---

## ⚠️ DB 연결 설정 — 담당자 필독

> 확인 일시: 2026-03-12 / 확인자: 조장(dhwang0803)

### 현재 VPC PostgreSQL 설정값

| 파라미터 | 현재값 | 환산 |
|----------|--------|------|
| `shared_buffers` | 131072 × 8kB | **1 GB** |
| `work_mem` | 32768 kB | **32 MB** |
| `max_connections` | 100 | **100개** |
| `max_parallel_workers_per_gather` | 0 | **병렬 쿼리 비활성화** |

### 설정 변경 필요 여부

| 파라미터 | 변경 필요 | 판단 근거 |
|----------|----------|----------|
| `shared_buffers` | ❌ 불필요 | Gold MV 캐싱에 충분 |
| `work_mem` | ❌ 불필요 | PK 단순 조회 — 4MB도 충분 |
| `max_parallel_workers_per_gather` | ❌ 불필요 | Gold MV는 index scan, 병렬 불필요 |
| `max_connections` | ❌ DB 변경 불필요 | **API 서버 커넥션 풀로 해결** (아래 참고) |

### 🔶 max_connections 주의사항

현재 100개 제한 중 팀원 백그라운드 작업(크롤러·임베딩)이 약 20~25개를 점유하고 있다.
API 서버가 요청마다 새 연결을 열면 트래픽 spike 시 `FATAL: too many connections` 에러 발생.

**필수 조치 — API 서버에서 커넥션 풀 명시적 제한:**

```python
# app/main.py 또는 app/services/db.py
import asyncpg, os

async def get_pool():
    return await asyncpg.create_pool(
        os.getenv("DATABASE_URL"),
        min_size=2,
        max_size=10,   # 100 - (팀원 연결 ~25) 여유분에서 보수적 설정
    )
```

> `max_size=10` 기준: 동시 연결 25개(팀원) + 풀 10개 + 예약 5개 = 40개 → 여유 60개 확보.
> API 서버를 수평 확장(인스턴스 추가)할 경우 PgBouncer 도입 검토 필요.

### 🔶 MV 갱신 시 주의사항

`max_parallel_workers_per_gather = 0` 이므로 `REFRESH CONCURRENTLY` 속도가 느리다.
API 서버 운영과는 직접 무관하나, **MV 갱신 배치 주기 설계 시 반영 필요.**
갱신 지연 → Gold 데이터 stale → 추천 결과 최신성 저하로 이어진다.
