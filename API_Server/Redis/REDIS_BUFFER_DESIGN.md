# Redis 실시간 유저 데이터 버퍼 설계

> 작성일: 2026-03-20
> **상태: 폐기 (2026-03-21)** — 인프라 제약(1GB RAM VPC)으로 Redis 도입 불가.
> 대체 설계: `API_Server/docs/realtime_architecture.md` (방안 A — PG 내장 기능 + 인메모리 버퍼)

---

## 1. 배경

Frontend + API Server 설계가 진행되면서 실시간 유저 데이터 처리 필요성이 발생했다.
시청 진행률 등 빈번한 쓰기를 Redis에 임시 저장하고, 매일 자정 정제 후 RDS(PostgreSQL)에 적재하는 구조를 검토한다.

---

## 2. 현재 실시간 쓰기 지점 분석

| 엔드포인트 | 테이블 | 쓰기 패턴 | Redis 버퍼링 |
|-----------|--------|-----------|-------------|
| `POST /series/.../progress` | `episode_progress` | 시청 중 반복 UPSERT | **적합** |
| `POST /purchases` | `purchase_history` + `point_history` | 구매 시 트랜잭션 INSERT | **부적합** (정합성 필수) |
| `POST /wishlist` | `wishlist` | 찜 추가/삭제 | **부적합** (빈도 낮음, 즉시 반영 필요) |
| (ML 파이프라인) | `watch_history` | 배치 적재 | **적합** (이벤트 로그) |

### Redis 버퍼링이 부적합한 이유

- **purchase_history / point_history**: 포인트 잔액이 `SUM(point_history)` 집계로 산출됨. Redis에 버퍼링하면 이중 구매, 잔액 불일치 위험
- **wishlist**: 쓰기 빈도가 낮고 즉시 UI 반영이 UX상 필요

---

## 3. 아키텍처

```
┌─────────────┐     ┌───────────────────────┐     ┌──────────────┐
│  Frontend   │────▶│  FastAPI (API_Server)  │────▶│  PostgreSQL  │
│  (STB/Web)  │     │                       │     │  (RDS/VPC)   │
└─────────────┘     └───────┬───────────────┘     └──────▲───────┘
                            │                            │
                    실시간 시청 로그                  자정 배치
                            │                            │
                     ┌──────▼──────┐              ┌──────┴───────┐
                     │    Redis    │─────────────▶│  Batch Job   │
                     │  (버퍼)     │              │  (정제+적재)  │
                     └─────────────┘              └──────────────┘
```

### 데이터 흐름

1. **실시간**: Frontend → API Server → Redis (시청 진행률, 시청 이벤트 로그)
2. **트랜잭션**: Frontend → API Server → PostgreSQL 직접 (구매, 포인트, 찜)
3. **배치**: Redis → Batch Job (자정) → PostgreSQL
4. **읽기**: API Server → Redis 우선 조회 → DB fallback

---

## 4. Redis 키 설계

### 4.1 시청 진행률 (episode_progress 버퍼)

최신 값만 유지 (HASH).

```
KEY:   ep_progress:{user_id}:{vod_id}
TYPE:  HASH

FIELDS:
  completion_rate   INT (0-100)
  watched_at        TIMESTAMPTZ (ISO 8601)
  series_nm         VARCHAR

EXAMPLE:
  HSET ep_progress:U001:V001 completion_rate 75 watched_at "2026-03-20T14:30:00Z" series_nm "시그널"
```

### 4.2 시청 이벤트 로그 (watch_history 원천 — ML용)

이벤트 누적 (LIST).

```
KEY:   watch_log:{user_id}
TYPE:  LIST

VALUE: JSON object
  {
    "vod_id": "V001",
    "strt_dt": "2026-03-20T14:00:00Z",
    "use_tms": 1200,
    "completion_rate": 0.85
  }

EXAMPLE:
  LPUSH watch_log:U001 '{"vod_id":"V001","strt_dt":"...","use_tms":1200,"completion_rate":0.85}'
```

### 4.3 (선택) 실시간 인기도 카운터

```
KEY:   trending:{ct_cl}
TYPE:  SORTED SET

EXAMPLE:
  ZINCRBY trending:movie 1 "V001"
  ZINCRBY trending:drama 1 "V002"
```

---

## 5. 자정 배치 잡

### 처리 순서

```
1. episode_progress 동기화
   - Redis HSCAN ep_progress:* → PostgreSQL UPSERT
   - ON CONFLICT (user_id_fk, vod_id_fk) UPDATE SET completion_rate, watched_at

2. watch_history 적재
   - Redis LPOP watch_log:* → 정제 (중복 제거, use_tms 합산)
   - PostgreSQL INSERT ... ON CONFLICT (user_id_fk, vod_id_fk, strt_dt) DO NOTHING

3. Materialized View 갱신
   - REFRESH MATERIALIZED VIEW CONCURRENTLY serving.mv_daily_watch_stats
   - REFRESH MATERIALIZED VIEW CONCURRENTLY serving.mv_vod_watch_stats

4. Redis 키 정리
   - 동기화 완료된 ep_progress:* 키 삭제
   - watch_log:* 비워진 키 삭제
   - trending:* 초기화 (일간)
```

### 데이터 포맷 변환

| 필드 | Redis (원본) | episode_progress (API용) | watch_history (ML용) |
|------|-------------|------------------------|---------------------|
| completion_rate | 75 (INT) | 75 (SMALLINT 0-100) | 0.75 (REAL 0.0-1.0) |
| 시청 시각 | watched_at (ISO) | watched_at (TIMESTAMPTZ) | strt_dt (TIMESTAMP) |

---

## 6. API 읽기 경로 변경

Redis 도입 후 시청 관련 API는 **Redis 우선 조회 → DB fallback** 패턴으로 변경해야 한다.

### 영향 받는 엔드포인트

| 엔드포인트 | 현재 (DB 직접) | 변경 후 |
|-----------|---------------|--------|
| `GET /user/me/watching` | episode_progress (1-99%) | Redis ep_progress:* 먼저 → DB fallback |
| `GET /user/me/history` | episode_progress 전체 | Redis + DB 병합 |
| `GET /series/{nm}/progress` | episode_progress WHERE series | Redis 필터 + DB fallback |

### 영향 없는 엔드포인트 (DB 직접 유지)

- `GET /user/me/profile` — point_history SUM (트랜잭션 데이터)
- `GET /user/me/points` — point_history
- `GET /user/me/purchases` — purchase_history
- `GET /user/me/wishlist` — wishlist
- `POST /purchases` — 트랜잭션

---

## 7. 장애 대응

### Redis 다운 시 fallback

```python
async def update_progress(user_id, vod_id, completion_rate):
    try:
        await redis.hset(f"ep_progress:{user_id}:{vod_id}", mapping={...})
    except RedisError:
        # fallback: DB 직접 UPSERT (기존 로직)
        await db_upsert_episode_progress(user_id, vod_id, completion_rate)
```

### 배치 잡 실패 시

- 배치 잡은 멱등성(idempotent) 보장 — ON CONFLICT 활용
- 실패 시 Redis 데이터는 보존되고 다음 배치에서 재처리
- TTL은 설정하지 않음 (배치 성공 후에만 삭제)

---

## 8. 미결 사항

- [ ] Redis 인프라 위치 결정 (VPC 내부 / 외부)
- [ ] 브랜치 분기 여부 (API_Server 내 통합 vs 별도 브랜치)
- [ ] 배치 스케줄러 선택 (APScheduler / cron / Celery Beat)
- [ ] Redis 메모리 용량 산정 (동시 접속 사용자 수 기반)
- [ ] trending 카운터 활용 범위 (mv_daily_watch_stats 대체 여부)
