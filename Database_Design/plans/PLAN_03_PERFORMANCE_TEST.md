# Phase 3: 성능 검증 계획

**단계**: Phase 3 / 5
**목표**: 주요 조회 패턴에 대한 성능 목표 달성 확인
**산출물**: `tests/performance_test.sql`, `tests/test_results.md`

---

## 1. 성능 목표

| 조회 패턴 | 목표 응답시간 | 기준 |
|----------|------------|------|
| 사용자별 시청이력 조회 | < 100ms | user_id_fk 인덱스 활용 |
| VOD별 시청 통계 조회 | < 100ms | vod_id_fk 인덱스 활용 |
| 날짜 범위 시청 조회 | < 500ms | strt_dt 인덱스 활용 |
| 만족도 상위 VOD 조회 | < 500ms | satisfaction 인덱스 활용 |

---

## 2. 테스트 쿼리 (performance_test.sql)

### 테스트 1: 사용자별 시청이력 조회
```sql
-- 목표: < 100ms
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    wh.watch_history_id,
    wh.vod_id_fk,
    v.asset_nm,
    v.genre,
    wh.strt_dt,
    wh.use_tms,
    wh.completion_rate,
    wh.satisfaction
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE wh.user_id_fk = '0000f3514448d06cddfb916d39bcee86560093ee1d3ea475c8c33b3dac8a18e4'
ORDER BY wh.strt_dt DESC;

-- 확인 포인트:
-- 1. Index Scan on idx_wh_user_id 사용 여부
-- 2. Rows 추정치 vs 실제 값 차이
-- 3. 총 실행 시간 (Execution Time)
```

### 테스트 2: VOD별 시청 통계 조회
```sql
-- 목표: < 100ms
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    vod_id_fk,
    COUNT(*) AS total_views,
    COUNT(DISTINCT user_id_fk) AS unique_viewers,
    AVG(completion_rate) AS avg_completion,
    AVG(satisfaction) AS avg_satisfaction,
    MAX(strt_dt) AS last_viewed
FROM watch_history
WHERE vod_id_fk = 'cjc|M4996864LFOL10619201'
GROUP BY vod_id_fk;
```

### 테스트 3: 날짜 범위 시청 조회
```sql
-- 목표: < 500ms
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    COUNT(*) AS total_views,
    COUNT(DISTINCT user_id_fk) AS daily_active_users,
    AVG(completion_rate) AS avg_completion
FROM watch_history
WHERE strt_dt BETWEEN '2023-01-01 00:00:00+00' AND '2023-01-07 23:59:59+00';
```

### 테스트 4: 만족도 상위 VOD 조회
```sql
-- 목표: < 500ms
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    v.ct_cl,
    AVG(wh.satisfaction) AS avg_satisfaction,
    COUNT(wh.watch_history_id) AS view_count
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
WHERE wh.satisfaction > 0
GROUP BY v.full_asset_id, v.asset_nm, v.genre, v.ct_cl
HAVING COUNT(wh.watch_history_id) >= 10
ORDER BY avg_satisfaction DESC
LIMIT 100;
```

### 테스트 5: 복합 인덱스 활용 (사용자별 시간순)
```sql
-- 목표: < 100ms
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    user_id_fk,
    vod_id_fk,
    strt_dt,
    satisfaction
FROM watch_history
WHERE user_id_fk = '0000f3514448d06cddfb916d39bcee86560093ee1d3ea475c8c33b3dac8a18e4'
  AND strt_dt >= '2023-01-01 00:00:00+00'
ORDER BY strt_dt DESC;
-- idx_wh_user_strt (user_id_fk, strt_dt) 복합 인덱스 활용 기대
```

### 테스트 6: 연령대별 VOD 추천 (세그멘테이션)
```sql
-- 목표: < 500ms
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    COUNT(*) AS view_count,
    AVG(wh.satisfaction) AS avg_sat
FROM watch_history wh
JOIN "user" u ON wh.user_id_fk = u.sha2_hash
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE u.age_grp10 = '30대'
  AND wh.satisfaction > 0.6
GROUP BY v.full_asset_id, v.asset_nm, v.genre
HAVING COUNT(*) >= 5
ORDER BY avg_sat DESC
LIMIT 50;
```

---

## 3. EXPLAIN ANALYZE 해석 가이드

### 좋은 실행 계획 신호
- `Index Scan` 또는 `Index Only Scan` 사용
- `Rows Removed by Filter` 값이 낮음
- `Buffers: shared hit` 비율이 높음 (캐시 히트)
- `Execution Time` < 목표 시간

### 나쁜 실행 계획 신호
- `Seq Scan` (순차 스캔) → 인덱스 미활용
- `Nested Loop` + 대용량 테이블 조합
- `Hash Join` 메모리 부족 (work_mem 조정 필요)

### 최적화 방법
```sql
-- 통계 갱신 (인덱스 선택 개선)
ANALYZE watch_history;
ANALYZE vod;
ANALYZE "user";

-- 쿼리 플래너 힌트 (work_mem 증가)
SET work_mem = '256MB';

-- 파티셔닝 여부 확인 (미래 최적화)
```

---

## 4. 인덱스 유효성 확인

```sql
-- 생성된 인덱스 목록 확인
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename IN ('user', 'vod', 'watch_history')
ORDER BY tablename, indexname;

-- 인덱스 사용률 확인 (적재 후)
SELECT
    schemaname,
    tablename,
    indexname,
    idx_scan AS scans,
    idx_tup_read AS tuples_read
FROM pg_stat_user_indexes
WHERE tablename IN ('user', 'vod', 'watch_history')
ORDER BY idx_scan DESC;
```

---

## 5. 테이블 크기 확인

```sql
-- 테이블 및 인덱스 크기
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(relid)) AS total_size,
    pg_size_pretty(pg_relation_size(relid)) AS table_size,
    pg_size_pretty(pg_total_relation_size(relid) - pg_relation_size(relid)) AS index_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN ('user', 'vod', 'watch_history')
ORDER BY pg_total_relation_size(relid) DESC;
```

### 예상 크기 (설계 기준)
| 테이블 | 데이터 크기 | 인덱스 크기 |
|--------|-----------|-----------|
| watch_history | ~300-400MB | ~100-150MB |
| user | ~20-30MB | ~5MB |
| vod | ~30-50MB | ~10MB |

---

## 6. 성능 개선 여지 (목표 미달 시)

### 방법 1: 파티셔닝 (watch_history)
```sql
-- strt_dt 기준 연도별 파티셔닝
-- Phase 4 또는 별도 최적화 단계에서 구현
CREATE TABLE watch_history_2023
    PARTITION OF watch_history
    FOR VALUES FROM ('2023-01-01') TO ('2024-01-01');
```

### 방법 2: 부분 인덱스 (satisfaction > 0)
```sql
-- 만족도 0 초과인 레코드만 인덱스
CREATE INDEX idx_wh_satisfaction_nonzero
    ON watch_history (satisfaction)
    WHERE satisfaction > 0;
```

### 방법 3: 커버링 인덱스 (Index Only Scan 유도)
```sql
-- 사용자별 최근 시청 쿼리 최적화
CREATE INDEX idx_wh_user_covering
    ON watch_history (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);
```

---

**이전 단계**: PLAN_02_DATA_MIGRATION.md
**다음 단계**: PLAN_04_EXTENSION_TABLES.md
