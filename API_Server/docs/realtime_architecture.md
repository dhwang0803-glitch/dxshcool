# 실시간 유저 데이터 처리 아키텍처

> 작성일: 2026-03-21
> 상태: 확정 (방안 A — Redis 없이 PG 내장 기능 + 인메모리 버퍼)
> 이전 문서: `API_Server/Redis/REDIS_BUFFER_DESIGN.md` (Redis 기반, 폐기)

---

## 1. 배경

### 인프라 제약

| VPC | CPU | RAM | 현재 점유 | 여유 |
|-----|-----|-----|----------|------|
| DB | 1 core | 1GB (+swap 3GB) | PostgreSQL shared_buffers=1GB (swap 의존) | 거의 없음 |
| API Server | 1 core | 1GB | FastAPI + uvicorn + asyncpg pool | ~300-400MB |
| Frontend | Cloud Run Service | 가변 | — | GCP 관리형 |

Redis 추가 시 API Server VPC에서 OOM 위험, DB VPC는 불가능.
**PostgreSQL 내장 기능(LISTEN/NOTIFY, 트리거) + FastAPI 인메모리 버퍼**로 해결한다.

### 처리 대상 유저 활동

| # | 활동 | 빈도 | 필요 메커니즘 |
|---|------|------|-------------|
| 1 | 시청 진행률 heartbeat | 30초마다 (고빈도) | 인메모리 버퍼 → 배치 flush |
| 2 | VOD 재생 → 시청/구매 내역 즉시 반영 | 이벤트성 | DB 직접 쓰기 + NOTIFY |
| 3 | 포인트 잔액 조회 | 프로필/구매 시 | 캐시 컬럼 + 트리거 |
| 4 | 시청예약 등록 + 알림 push | 이벤트성 | DB + background task + WebSocket |
| 5 | 찜 추가/해제 | 이벤트성 | DB 직접 쓰기 |

---

## 2. 아키텍처

```
┌─────────────┐     ┌────────────────────────────────────┐     ┌──────────────┐
│  셋톱박스    │────▶│  FastAPI (API Server VPC)           │────▶│  PostgreSQL  │
│  Frontend   │◀────│                                    │◀────│  (DB VPC)    │
│  Cloud Run  │     │  ┌──────────────────────┐          │     │              │
└─────────────┘     │  │ 인메모리 버퍼         │          │     │  TRIGGER     │
      ▲             │  │ _progress_buffer     │──60s───▶│     │  ├─ point_balance 갱신
      │             │  │ (heartbeat 수집)     │  flush   │     │  └─ NOTIFY 발행
      │             │  └──────────────────────┘          │     │              │
      │             │                                    │     └──────────────┘
      │             │  ┌──────────────────────┐          │            │
      │             │  │ PG LISTEN            │◀─────────│────────────┘
      └─────────────│──│ → WebSocket push     │          │     NOTIFY 'user_activity'
                    │  └──────────────────────┘          │     NOTIFY 'reservation_alert'
                    │                                    │
                    │  ┌──────────────────────┐          │
                    │  │ Background Task      │          │
                    │  │ (30초 주기)           │          │
                    │  │ → 시청예약 알림 체크   │          │
                    │  └──────────────────────┘          │
                    └────────────────────────────────────┘
```

### 데이터 흐름

| 흐름 | 경로 | 지연 |
|------|------|------|
| heartbeat 수신 | Frontend → FastAPI 메모리 | <1ms |
| heartbeat 저장 | 메모리 → PostgreSQL (60초 batch) | 10-20ms (백그라운드) |
| 구매/찜/시청 | Frontend → FastAPI → PostgreSQL 직접 | 5-30ms |
| 마이페이지 갱신 알림 | PG TRIGGER → NOTIFY → FastAPI LISTEN → WebSocket | 3-10ms |
| 시청예약 알림 | Background task → WebSocket push | 5-10ms |
| 포인트 잔액 조회 | user.point_balance 캐시 컬럼 SELECT | 2-3ms |

---

## 3. 구현 상세

### 3-1. Heartbeat 인메모리 버퍼

시청 중 30초마다 호출되는 `POST /series/{nm}/episodes/{nm}/progress`를
매번 DB에 쓰지 않고 메모리에 최신 값만 보관, 60초마다 일괄 저장.

```python
# app/services/progress_buffer.py

import asyncio
from app.services.db import get_pool

# (user_id, vod_id) → {"completion_rate": int, "series_nm": str}
_buffer: dict[tuple[str, str], dict] = {}
_lock = asyncio.Lock()

async def buffer_progress(user_id: str, vod_id: str, series_nm: str, rate: int):
    """heartbeat 수신 → 메모리에 최신 값만 보관."""
    async with _lock:
        _buffer[(user_id, vod_id)] = {
            "completion_rate": rate,
            "series_nm": series_nm,
        }

async def flush_progress():
    """60초마다 호출 — 버퍼를 DB에 일괄 UPSERT 후 비움."""
    async with _lock:
        items = list(_buffer.items())
        _buffer.clear()

    if not items:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO public.episode_progress
                (user_id_fk, vod_id_fk, series_nm, completion_rate, watched_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id_fk, vod_id_fk)
            DO UPDATE SET completion_rate = $4, watched_at = NOW()
            """,
            [(uid, vid, d["series_nm"], d["completion_rate"]) for (uid, vid), d in items],
        )
```

**효과**: DB 쓰기 횟수 = 동시 시청자 수 / 60초 (30초 heartbeat 대비 절반으로 감소)
**유실 범위**: FastAPI 재시작 시 최대 60초분 (허용 가능 — 진행률 수% 차이)

### 3-2. point_balance 캐시 컬럼 + 트리거

`GET /user/me/profile` 호출마다 `SUM(point_history)` 집계 대신,
`user` 테이블에 캐시 컬럼을 두고 트리거로 자동 갱신.

```sql
-- Database_Design 마이그레이션
ALTER TABLE public."user" ADD COLUMN point_balance INTEGER NOT NULL DEFAULT 0;

-- 초기값 세팅
UPDATE public."user" u SET point_balance = (
    SELECT COALESCE(SUM(CASE WHEN type = 'earn' THEN amount ELSE -amount END), 0)
    FROM public.point_history WHERE user_id_fk = u.sha2_hash
);

-- 자동 갱신 트리거
CREATE OR REPLACE FUNCTION fn_update_point_balance() RETURNS TRIGGER AS $$
BEGIN
    UPDATE public."user"
    SET point_balance = point_balance +
        CASE WHEN NEW.type = 'earn' THEN NEW.amount ELSE -NEW.amount END
    WHERE sha2_hash = NEW.user_id_fk;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_point_balance
    AFTER INSERT ON public.point_history
    FOR EACH ROW EXECUTE FUNCTION fn_update_point_balance();
```

**효과**: SUM 집계 O(N) → PK 조회 O(1). 10만 건 point_history에서도 ~2ms.
**정합성**: 트리거가 트랜잭션 내에서 실행되므로 point_history INSERT와 원자적.

### 3-3. PG LISTEN/NOTIFY — 마이페이지 즉시 갱신

구매/찜/시청 완료 시 Frontend가 마이페이지 데이터를 실시간 refetch하도록 WebSocket으로 알림.

```sql
-- Database_Design: NOTIFY 발행 트리거
CREATE OR REPLACE FUNCTION fn_notify_user_activity() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('user_activity', json_build_object(
        'user_id', NEW.user_id_fk,
        'table', TG_TABLE_NAME,
        'action', TG_OP
    )::text);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_notify_purchase
    AFTER INSERT ON public.purchase_history
    FOR EACH ROW EXECUTE FUNCTION fn_notify_user_activity();

CREATE TRIGGER trg_notify_wishlist
    AFTER INSERT OR DELETE ON public.wishlist
    FOR EACH ROW EXECUTE FUNCTION fn_notify_user_activity();
```

```python
# app/services/pg_listener.py — FastAPI 측 수신

async def start_pg_listener():
    """lifespan에서 시작. PG NOTIFY 수신 → WebSocket push."""
    pool = await get_pool()
    conn = await pool.acquire()

    async def on_user_activity(conn, pid, channel, payload):
        import json
        data = json.loads(payload)
        user_id = data["user_id"]
        # WebSocket으로 마이페이지 갱신 알림 전송
        from app.routers.ad import _connections
        ws = _connections.get(user_id)
        if ws:
            await ws.send_json({
                "type": "data_updated",
                "table": data["table"],
                "action": data["action"],
            })

    await conn.add_listener('user_activity', on_user_activity)
```

**Frontend 동작**: `data_updated` 메시지 수신 → 해당 섹션 API 재호출 (refetch)

### 3-4. 시청예약 + 알림

```sql
-- Database_Design: watch_reservation 테이블
CREATE TABLE public.watch_reservation (
    reservation_id  BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk      VARCHAR(64)  NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    channel         SMALLINT     NOT NULL,
    program_name    VARCHAR(200) NOT NULL,
    alert_at        TIMESTAMPTZ  NOT NULL,
    notified        BOOLEAN      NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),

    CONSTRAINT chk_wr_channel CHECK (channel >= 1)
);

CREATE INDEX idx_wr_pending ON public.watch_reservation (alert_at)
    WHERE notified = FALSE;
```

```python
# app/services/reservation_checker.py

async def check_reservations():
    """30초마다 호출 — 도래한 예약 알림 전송."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            UPDATE public.watch_reservation
            SET notified = TRUE
            WHERE alert_at <= NOW() AND notified = FALSE
            RETURNING user_id_fk, channel, program_name
        """)

    from app.routers.ad import _connections
    for row in rows:
        ws = _connections.get(row["user_id_fk"])
        if ws:
            await ws.send_json({
                "type": "reservation_alert",
                "channel": row["channel"],
                "program_name": row["program_name"],
                "message": f"채널 {row['channel']}번에서 {row['program_name']}이 곧 시작됩니다",
            })
```

---

## 4. Background Task 등록

```python
# app/main.py lifespan에 추가

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_pool()
    # background tasks 시작
    task_flush = asyncio.create_task(_periodic_flush())
    task_reservation = asyncio.create_task(_periodic_reservation_check())
    task_listener = asyncio.create_task(start_pg_listener())
    yield
    # 종료 시 정리
    task_flush.cancel()
    task_reservation.cancel()
    task_listener.cancel()
    await flush_progress()  # 잔여 버퍼 최종 flush
    await close_pool()

async def _periodic_flush():
    while True:
        await asyncio.sleep(60)
        await flush_progress()

async def _periodic_reservation_check():
    while True:
        await asyncio.sleep(30)
        await check_reservations()
```

---

## 5. 성능 예상 (10명 동시 접속)

### 엔드포인트별 응답 시간

| 엔드포인트 | 현행 | 개선 후 | 변화 |
|-----------|------|--------|------|
| `GET /user/me/profile` | 5-15ms (SUM) | **2-3ms** (캐시 컬럼) | -70% |
| `POST /progress` (heartbeat) | 5-10ms (DB) | **<1ms** (메모리) | -90% |
| `GET /user/me/points` | 8-20ms (SUM+목록) | **5-10ms** (캐시+목록) | -50% |
| 기타 GET | 5-25ms | 5-25ms | 변화 없음 |

### 동시성 분석

```
10명 동시 접속 시:
├── 평균 QPS: ~0.6 req/s (페이지 이동 + heartbeat)
├── 피크 QPS: ~10 req/s (전원 동시 페이지 이동)
├── asyncpg pool: max=10 → 커넥션 여유 ✅
├── heartbeat DB 쓰기: 0회/30초 → 10회/60초 (batch) ✅
└── 전체 응답: 100ms 이내 보장
```

### 체감 시나리오

| 유저 행동 | 응답 시간 | 체감 |
|----------|----------|------|
| 홈 진입 | ~30-50ms | 즉시 |
| 시리즈 상세 | ~20-40ms | 즉시 |
| 재생 중 heartbeat | <1ms | 무감지 |
| 구매 완료 → 마이페이지 반영 | ~30ms (구매) + ~5ms (NOTIFY) | 즉시 |
| 시청예약 알림 수신 | ~5-10ms | 즉시 |

---

## 6. Database_Design 브랜치 필요 작업

| # | 작업 | 파일 |
|---|------|------|
| 1 | `user.point_balance` 캐시 컬럼 + 트리거 | 마이그레이션 신규 |
| 2 | `watch_reservation` 테이블 생성 | 마이그레이션 신규 |
| 3 | `fn_notify_user_activity` 트리거 | 마이그레이션 신규 |

---

## 7. 스케일 전환 기준

현재 아키텍처에서 아래 조건 충족 시 Redis 또는 Cloud Pub/Sub 전환 검토:

| 조건 | 현행 유지 | 전환 검토 |
|------|----------|----------|
| API Server 인스턴스 | 1대 | **2대 이상** (인메모리 버퍼 공유 불가) |
| 동시 시청자 | ~500명 | **500명 초과 지속** |
| RAM | 1GB | **2GB 이상 확보 시** |
| 알림 복잡도 | 시청예약 1종 | **다채널 알림 (이메일/SMS 등)** |

---

## 8. 이전 설계 대비 변경점

| 항목 | 이전 (Redis 기반) | 현재 (방안 A) |
|------|-----------------|-------------|
| 실시간 캐시 | Redis HASH/LIST | FastAPI 인메모리 dict |
| 배치 적재 | Redis → 자정 배치 → PG | 인메모리 → 60초 flush → PG |
| 포인트 잔액 | SUM 집계 (매번) | user.point_balance 캐시 컬럼 + 트리거 |
| 이벤트 알림 | 미설계 | PG LISTEN/NOTIFY + WebSocket |
| 시청예약 알림 | 미설계 | background task + WebSocket |
| 추가 인프라 | Redis 프로세스 필요 | **불필요** |
| 장애 포인트 | Redis 다운 시 fallback | 단일 프로세스, 장애점 감소 |
