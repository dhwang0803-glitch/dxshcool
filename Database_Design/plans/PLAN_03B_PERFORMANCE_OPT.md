# Phase 3B: 성능 개선 계획

**단계**: Phase 3B (Phase 3 → Phase 4 사이 성능 개선)
**목표**: Phase 3 미적용 최적화 3가지 실제 적용 및 성능 목표 재달성
**산출물**: `schema/create_opt_indexes.sql`, `schema/create_materialized_views.sql`, `schema/partition_watch_history.sql`
**선행 조건**: Phase 3 완료 (VPC 설정: shared_buffers=1GB / work_mem=32MB / max_parallel_workers_per_gather=0)

---

## 1. 개선 항목 개요

| 항목 | 대상 쿼리 | 방법 | 위험도 | 작업 방식 |
|------|---------|------|-------|---------|
| OPT-1 | P01, P04 | 커버링 인덱스 + 부분 인덱스 | 낮음 | 온라인 (CONCURRENTLY) |
| OPT-2 | P04, P06 | Materialized View | 낮음 | 온라인 |
| OPT-3 | P03 | 파티셔닝 | 높음 | 오프라인 (팀 협의 필요) |

**작업 순서**: OPT-1 → OPT-2 → OPT-3 (각 항목 독립 실행 가능, OPT-3는 마지막에)

---

## 2. OPT-1: 커버링 인덱스 + 부분 인덱스

### 배경

**P01 현재 문제 (1,051ms cold / 4,262ms warm)**
```
Index Scan on watch_history (7,181 rows)
→ Hash Build on vod Seq Scan (166K rows) : 4,067ms (warm에서도 CPU 처리 시간)
→ Hash Join
```
vod(82MB)가 완전히 캐시되어도 Seq Scan + Hash Build에 CPU 4,067ms 소요.
커버링 인덱스 도입 시 플래너가 Nested Loop로 전환:
```
Index Scan on idx_wh_user_covering (watch_history, 7,181 rows, 정렬 포함)
→ vod_pkey Index Scan × 7,181회 ≈ 7,181 × 0.2ms ≈ 1,436ms (예상)
```

**P04 현재 문제 (41,336ms cold)**
```
Seq Scan on watch_history (satisfaction > 0 = 2,985,569 rows) : 27,490ms
```
부분 인덱스로 heap scan 대신 index scan 유도. 단, 대상이 전체의 75%이므로 효과 제한적.
근본 해결은 OPT-2 Materialized View.

### 실행 SQL

```sql
-- [OPT-1-A] 커버링 인덱스: P01 개선 (정렬 + JOIN 최적화)
-- 목적: idx_wh_user_id 대체, strt_dt 정렬 불필요, Nested Loop 유도
-- 예상 시간: 30~60분 (4M rows, CONCURRENTLY로 운영 중 실행 가능)
CREATE INDEX CONCURRENTLY idx_wh_user_covering
    ON watch_history (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);

-- [OPT-1-B] 부분 인덱스: P04 satisfaction > 0 필터 최적화
-- 목적: 2.98M rows 대상 scan을 인덱스로 유도
-- 주의: 대상이 전체 75%이므로 planner가 Seq Scan 선호할 수 있음 → MV로 보완
CREATE INDEX CONCURRENTLY idx_wh_satisfaction_nonzero
    ON watch_history (satisfaction DESC)
    WHERE satisfaction > 0;
```

### 주의사항

- `CONCURRENTLY`는 트랜잭션 내에서 실행 불가 (autocommit 상태에서 실행)
- 인덱스 생성 중 watch_history 쓰기는 정상 진행 (읽기 락 없음)
- OPT-1-A 완료 후 기존 `idx_wh_user_id` 제거 여부 검토:
  - `idx_wh_user_covering`이 `idx_wh_user_id` 역할 포함 → 중복 제거 가능
  - 단, `idx_wh_user_covering` 크기가 더 크므로 trade-off 확인 후 결정

### 테스트 검증

```sql
-- OPT-1-A 적용 후 P01 재실행
EXPLAIN (ANALYZE, BUFFERS)
SELECT wh.watch_history_id, wh.vod_id_fk, v.asset_nm, v.genre,
       wh.strt_dt, wh.use_tms, wh.completion_rate, wh.satisfaction
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE wh.user_id_fk = 'c895f6cd9f2027aedf31c3236aa9e9b05613b87b0fb5fd5f856d4003c9c9f072'
ORDER BY wh.strt_dt DESC;

-- 확인 포인트:
-- 1. idx_wh_user_covering Index Scan 사용 여부
-- 2. Sort 단계 제거 여부 (인덱스 순서와 쿼리 정렬 일치)
-- 3. Nested Loop 전환 여부 (Hash Join 대신)
-- 4. 목표: cold <500ms, warm <200ms
```

### 예상 효과

| 쿼리 | 현재 (0w cold) | 예상 후 | 변화 |
|------|--------------|---------|------|
| P01 | 1,051ms | <500ms | Nested Loop, Sort 제거 |
| P04 | 41,336ms | 효과 제한적 | MV로 대체 |

---

## 3. OPT-2: Materialized View

### 배경

**P04 (만족도 상위 VOD 조회)**: 2.98M rows 전체 집계 → 결과는 동일하므로 사전 계산
**P06 (연령대별 선호 VOD)**: 연령대 × VOD 집계 → watch_history 전체 스캔 불필요

Materialized View 조회 시: `SELECT * FROM mv WHERE ...` → 밀리초 단위 응답

### REFRESH 전략

| MV | REFRESH 주기 | 방법 | 이유 |
|----|------------|------|------|
| mv_vod_satisfaction_stats | 일 1회 | CONCURRENTLY | 만족도는 실시간 불필요 |
| mv_age_grp_vod_stats | 일 1회 | CONCURRENTLY | 연령대 집계는 실시간 불필요 |

- `CONCURRENTLY`: 읽기 락 없이 갱신 (운영 중 실행 가능), UNIQUE INDEX 필수
- REFRESH는 cron 또는 pg_cron 확장으로 자동화

### 실행 SQL

```sql
-- [OPT-2-A] mv_vod_satisfaction_stats: P04 대체
-- 목적: 만족도 상위 VOD 사전 집계
CREATE MATERIALIZED VIEW mv_vod_satisfaction_stats AS
SELECT
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    v.ct_cl,
    COUNT(wh.watch_history_id)      AS view_count,
    AVG(wh.satisfaction)            AS avg_satisfaction
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
WHERE wh.satisfaction > 0
GROUP BY v.full_asset_id, v.asset_nm, v.genre, v.ct_cl
HAVING COUNT(wh.watch_history_id) >= 10;

-- CONCURRENTLY REFRESH를 위한 UNIQUE INDEX 필수
CREATE UNIQUE INDEX ON mv_vod_satisfaction_stats (full_asset_id);

-- 조회 인덱스
CREATE INDEX ON mv_vod_satisfaction_stats (avg_satisfaction DESC);


-- [OPT-2-B] mv_age_grp_vod_stats: P06 대체
-- 목적: 연령대별 VOD 선호도 사전 집계
CREATE MATERIALIZED VIEW mv_age_grp_vod_stats AS
SELECT
    u.age_grp10,
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    COUNT(*)                AS view_count,
    AVG(wh.satisfaction)    AS avg_satisfaction
FROM watch_history wh
JOIN "user" u ON wh.user_id_fk = u.sha2_hash
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE wh.satisfaction > 0.6
GROUP BY u.age_grp10, v.full_asset_id, v.asset_nm, v.genre
HAVING COUNT(*) >= 5;

-- CONCURRENTLY REFRESH를 위한 UNIQUE INDEX 필수
CREATE UNIQUE INDEX ON mv_age_grp_vod_stats (age_grp10, full_asset_id);

-- 조회 인덱스
CREATE INDEX ON mv_age_grp_vod_stats (age_grp10, avg_satisfaction DESC);


-- [OPT-2-C] REFRESH 명령 (일 1회 실행)
-- CONCURRENTLY: 기존 데이터 유지하면서 갱신 (읽기 락 없음)
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_vod_satisfaction_stats;
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_age_grp_vod_stats;
```

### 대체 쿼리

```sql
-- P04 대체: mv_vod_satisfaction_stats 조회
SELECT full_asset_id, asset_nm, genre, ct_cl, avg_satisfaction, view_count
FROM mv_vod_satisfaction_stats
ORDER BY avg_satisfaction DESC
LIMIT 100;
-- 예상: <10ms (index scan on avg_satisfaction DESC)

-- P06 대체: mv_age_grp_vod_stats 조회
SELECT full_asset_id, asset_nm, genre, view_count, avg_satisfaction
FROM mv_age_grp_vod_stats
WHERE age_grp10 = '30대'
ORDER BY avg_satisfaction DESC
LIMIT 50;
-- 예상: <10ms (index scan on age_grp10, avg_satisfaction DESC)
```

### 주의사항

- MV 초기 생성 시 P04/P06 원본 쿼리 수준의 시간 소요 (41,336ms/21,120ms)
- 생성은 한 번만, 이후 REFRESH만 실행
- REFRESH CONCURRENTLY는 UNIQUE INDEX 없으면 실패
- Phase 5 추천 시스템과 MV 설계 정합성 사전 협의 권고 (MV 컬럼 추가 필요 시 DROP → 재생성 필요)

### 테스트 검증

```sql
-- MV 생성 확인
SELECT schemaname, matviewname, ispopulated
FROM pg_matviews
WHERE matviewname IN ('mv_vod_satisfaction_stats', 'mv_age_grp_vod_stats');

-- P04 대체 쿼리 성능
EXPLAIN (ANALYZE, BUFFERS)
SELECT full_asset_id, asset_nm, genre, ct_cl, avg_satisfaction, view_count
FROM mv_vod_satisfaction_stats
ORDER BY avg_satisfaction DESC LIMIT 100;
-- 목표: <10ms

-- P06 대체 쿼리 성능
EXPLAIN (ANALYZE, BUFFERS)
SELECT full_asset_id, asset_nm, genre, view_count, avg_satisfaction
FROM mv_age_grp_vod_stats
WHERE age_grp10 = '30대'
ORDER BY avg_satisfaction DESC LIMIT 50;
-- 목표: <10ms
```

### 예상 효과

| 쿼리 | 현재 (0w cold) | 예상 후 | 변화 |
|------|--------------|---------|------|
| P04 | 41,336ms | <10ms | MV 조회 |
| P06 | 21,120ms | <10ms | MV 조회 |

---

## 4. OPT-3: 파티셔닝 (팀 협의 필요)

### 배경

**P03 현재 문제 (26,611ms cold)**
```
Bitmap Index Scan on idx_wh_strt_dt (787,076 rows = 전체 19.7%)
→ Bitmap Heap Scan (55,018 heap blocks)
```
1주 데이터(787K rows)를 인덱스로 찾아도 heap block 55K개를 읽어야 함.
파티셔닝 적용 시 해당 월 파티션만 스캔 → 물리적 I/O 감소.

### 현재 데이터 분포 (2023년 1월 기준)

| 항목 | 수치 |
|------|------|
| 전체 시청이력 | 3,992,530건 |
| 2023-01-01~07 (1주) | 787,076건 (19.7%) |
| 2023-01 (1개월) 추정 | ~3,992,530건 전부 (단일 월) |

> **주의**: 현재 데이터가 2023-01 단일 월에 집중. 파티셔닝 효과는 다월 데이터 적재 후 극대화.

### 파티셔닝 전략

| 전략 | 설명 | 선택 |
|------|------|------|
| 월별 파티션 | watch_history_2023_01, _02 ... | 권장 |
| 연도별 파티션 | watch_history_2023, 2024 ... | 현재 데이터가 단일 월이므로 효과 미미 |

### 실행 절차 (오프라인 작업 — 팀 협의 후 실행)

```
Step 1: 새 파티션 테이블 생성 (watch_history_partitioned)
Step 2: 기존 watch_history 데이터 COPY → 새 테이블
Step 3: 인덱스 재생성 (파티션별 local index)
Step 4: 이름 교체 (watch_history → watch_history_old, watch_history_partitioned → watch_history)
Step 5: 검증 후 watch_history_old 제거
```

```sql
-- [OPT-3-1] 파티션 테이블 생성
CREATE TABLE watch_history_partitioned (
    -- 기존 watch_history와 동일한 컬럼
    watch_history_id    BIGSERIAL,
    user_id_fk          VARCHAR(64)     NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,
    strt_dt             TIMESTAMPTZ     NOT NULL,
    use_tms             INTEGER,
    completion_rate     REAL,
    satisfaction        DOUBLE PRECISION DEFAULT 0,
    created_at          TIMESTAMPTZ     DEFAULT NOW()
) PARTITION BY RANGE (strt_dt);

-- [OPT-3-2] 월별 파티션 생성 (데이터 범위에 맞게 추가)
CREATE TABLE watch_history_2023_01
    PARTITION OF watch_history_partitioned
    FOR VALUES FROM ('2023-01-01') TO ('2023-02-01');

CREATE TABLE watch_history_2023_02
    PARTITION OF watch_history_partitioned
    FOR VALUES FROM ('2023-02-01') TO ('2023-03-01');

-- 향후 데이터 범위까지 사전 생성 권장
-- CREATE TABLE watch_history_default
--     PARTITION OF watch_history_partitioned DEFAULT;  -- 범위 외 데이터 안전망

-- [OPT-3-3] 파티션별 인덱스 생성
CREATE INDEX ON watch_history_2023_01 (user_id_fk);
CREATE INDEX ON watch_history_2023_01 (vod_id_fk);
CREATE INDEX ON watch_history_2023_01 (strt_dt);
CREATE INDEX ON watch_history_2023_01 (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);
-- 나머지 파티션도 동일하게 생성

-- [OPT-3-4] 데이터 복사
INSERT INTO watch_history_partitioned
SELECT * FROM watch_history;

-- [OPT-3-5] 이름 교체 (트랜잭션 내 실행 권장)
BEGIN;
ALTER TABLE watch_history RENAME TO watch_history_old;
ALTER TABLE watch_history_partitioned RENAME TO watch_history;
COMMIT;

-- [OPT-3-6] 검증 후 제거
-- SELECT COUNT(*) FROM watch_history;      -- 3,992,530 확인
-- SELECT COUNT(*) FROM watch_history_old;  -- 동일 확인
-- DROP TABLE watch_history_old;
```

### 주의사항

- **팀 협의 필수**: watch_history 테이블명 참조하는 migrate.py, validate_data.py 등 모든 코드 영향
- **데이터 재적재 시간**: 4M rows COPY ≈ 10~30분 예상
- **인덱스 재생성 시간**: 파티션별 인덱스 총 1~2시간 예상
- **현재 데이터가 2023-01 단일 월**: 파티셔닝 즉시 효과 제한적. 다월 데이터 적재 후 P03 극적 개선 기대
- **제약조건 이전**: `uq_wh_user_vod_strt` UNIQUE 제약은 파티션 키(strt_dt) 포함이므로 파티션 테이블에서 그대로 동작

### 예상 효과

| 쿼리 | 현재 (0w cold) | 단일 월 데이터 | 다월 데이터 시 |
|------|--------------|-------------|-------------|
| P03 (1주) | 26,611ms | 효과 제한적 | <5,000ms (해당 파티션만 스캔) |

---

## 5. 실행 순서 및 체크리스트

### 권장 실행 순서

```
[즉시] OPT-1-A: idx_wh_user_covering 생성 (CONCURRENTLY)
[즉시] OPT-1-B: idx_wh_satisfaction_nonzero 생성 (CONCURRENTLY)
  ↓ 완료 후
[즉시] OPT-2-A: mv_vod_satisfaction_stats 생성 + UNIQUE INDEX
[즉시] OPT-2-B: mv_age_grp_vod_stats 생성 + UNIQUE INDEX
  ↓ 각 항목 성능 검증
[팀 협의] OPT-3: 파티셔닝 (오프라인 작업 일정 잡고 진행)
```

### 체크리스트

- [x] OPT-1-A: `idx_wh_user_covering` 생성 (576MB)
  - [x] P01 재실행 → random_page_cost=1.5와 함께 Nested Loop + Memoize 채택
  - [x] `idx_wh_user_id` 유지 결정 (planner가 OPT-1-A보다 선호 — 둘 다 공존)
  - **결과**: P01 cold 1,272ms → **128ms**, warm **28ms (PASS)**
- [x] OPT-1-B: `idx_wh_satisfaction_nonzero` 생성 (64MB)
  - [x] P04 재실행 → planner Seq Scan 선택 유지 (MV로 해결)
  - **추가 적용**: `random_page_cost=1.5` → P01 Nested Loop, P06 Nested Loop×2 채택
- [ ] OPT-2-A: `mv_vod_satisfaction_stats` 생성 + 인덱스
  - [ ] P04 대체 쿼리 <10ms 달성 확인
  - [ ] REFRESH CONCURRENTLY 동작 확인
- [ ] OPT-2-B: `mv_age_grp_vod_stats` 생성 + 인덱스
  - [ ] P06 대체 쿼리 <10ms 달성 확인
- [ ] OPT-3: 파티셔닝 (팀 협의 후)
  - [ ] 팀 내 작업 일정 공유
  - [ ] 파티션 테이블 생성 + 데이터 복사
  - [ ] 이름 교체 + 검증

---

## 6. 성능 목표 (Phase 3B 이후)

| 쿼리 | Phase 3 결과 | Phase 3B 목표 | 방법 |
|------|------------|-------------|------|
| P01 | 1,051ms cold | <500ms | OPT-1-A 커버링 인덱스 |
| P02 | 1,714ms warm | 현행 유지 | 개선 불필요 |
| P03 | 26,611ms | <5,000ms (다월 데이터 시) | OPT-3 파티셔닝 |
| P04 | 41,336ms | <10ms | OPT-2-A Materialized View |
| P05 | 9ms | 현행 유지 | 개선 불필요 |
| P06 | 21,120ms | <10ms | OPT-2-B Materialized View |

---

**이전 단계**: PLAN_03_PERFORMANCE_TEST.md
**다음 단계**: PLAN_04_EXTENSION_TABLES.md
