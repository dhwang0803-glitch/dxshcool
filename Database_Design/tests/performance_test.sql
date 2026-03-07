-- =============================================================
-- Phase 3 - 성능 테스트 (EXPLAIN ANALYZE)
-- 파일: Database_Design/tests/performance_test.sql
-- 목적: 주요 조회 패턴의 실행 계획 및 응답시간 검증
-- 작성일: 2026-03-07
-- 참조: PLAN_03_PERFORMANCE_TEST.md
-- =============================================================
-- 실행 방법: psql -U <user> -d <db> -f performance_test.sql
-- 성능 목표:
--   P01~P03, P05: < 100ms (인덱스 활용 단순 조회)
--   P04, P06:     < 500ms (집계/조인 쿼리)
-- =============================================================

-- 쿼리별 최대 실행 시간 제한 (개별 쿼리가 무한 대기하지 않도록)
SET statement_timeout = '120s';

-- 테이블 및 인덱스 크기 확인
SELECT
    relname                                                        AS table_name,
    pg_size_pretty(pg_total_relation_size(relid))                 AS total_size,
    pg_size_pretty(pg_relation_size(relid))                       AS table_size,
    pg_size_pretty(pg_total_relation_size(relid)
                   - pg_relation_size(relid))                     AS index_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname IN ('user', 'vod', 'watch_history')
ORDER BY pg_total_relation_size(relid) DESC;

-- 인덱스 목록 확인
SELECT tablename, indexname
FROM pg_indexes
WHERE tablename IN ('user', 'vod', 'watch_history')
ORDER BY tablename, indexname;


-- =============================================================
-- [P01] 사용자별 시청이력 조회
-- 목표: < 100ms | 기대 플랜: Index Scan on idx_wh_user_id
-- =============================================================
\echo '--- P01: 사용자별 시청이력 조회 ---'
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
WHERE wh.user_id_fk = 'c895f6cd9f2027aedf31c3236aa9e9b05613b87b0fb5fd5f856d4003c9c9f072'
ORDER BY wh.strt_dt DESC;


-- =============================================================
-- [P02] VOD별 시청 통계 조회
-- 목표: < 100ms | 기대 플랜: Index Scan on idx_wh_vod_id
-- =============================================================
\echo '--- P02: VOD별 시청 통계 조회 ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    vod_id_fk,
    COUNT(*)                    AS total_views,
    COUNT(DISTINCT user_id_fk)  AS unique_viewers,
    AVG(completion_rate)        AS avg_completion,
    AVG(satisfaction)           AS avg_satisfaction,
    MAX(strt_dt)                AS last_viewed
FROM watch_history
WHERE vod_id_fk = 'cjc|M5068430LFOL10619301'
GROUP BY vod_id_fk;


-- =============================================================
-- [P03] 날짜 범위 시청 조회 (1주)
-- 목표: < 500ms | 기대 플랜: Index Scan on idx_wh_strt_dt
-- =============================================================
\echo '--- P03: 날짜 범위 시청 조회 (1주) ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    COUNT(*)                        AS total_views,
    COUNT(DISTINCT user_id_fk)      AS daily_active_users,
    AVG(completion_rate)            AS avg_completion
FROM watch_history
WHERE strt_dt BETWEEN '2023-01-01 00:00:00+00' AND '2023-01-07 23:59:59+00';


-- =============================================================
-- [P04] 만족도 상위 VOD 조회 (집계 + JOIN)
-- 목표: < 500ms | 기대 플랜: satisfaction 인덱스 + Hash Join
-- =============================================================
\echo '--- P04: 만족도 상위 VOD 조회 ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    v.ct_cl,
    AVG(wh.satisfaction)            AS avg_satisfaction,
    COUNT(wh.watch_history_id)      AS view_count
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
WHERE wh.satisfaction > 0
GROUP BY v.full_asset_id, v.asset_nm, v.genre, v.ct_cl
HAVING COUNT(wh.watch_history_id) >= 10
ORDER BY avg_satisfaction DESC
LIMIT 100;


-- =============================================================
-- [P05] 복합 인덱스 활용 (사용자 + 날짜 범위)
-- 목표: < 100ms | 기대 플랜: Index Scan on idx_wh_user_strt
-- =============================================================
\echo '--- P05: 복합 인덱스 활용 (사용자+날짜) ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    user_id_fk,
    vod_id_fk,
    strt_dt,
    satisfaction
FROM watch_history
WHERE user_id_fk = 'c895f6cd9f2027aedf31c3236aa9e9b05613b87b0fb5fd5f856d4003c9c9f072'
  AND strt_dt >= '2023-01-01 00:00:00+00'
ORDER BY strt_dt DESC;


-- =============================================================
-- [P06] 연령대별 선호 VOD (3-테이블 JOIN + 집계)
-- 목표: < 500ms | 기대 플랜: idx_user_age_grp 활용
-- =============================================================
\echo '--- P06: 연령대별 선호 VOD ---'
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    COUNT(*)                AS view_count,
    AVG(wh.satisfaction)    AS avg_sat
FROM watch_history wh
JOIN "user" u ON wh.user_id_fk = u.sha2_hash
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE u.age_grp10 = '30대'
  AND wh.satisfaction > 0.6
GROUP BY v.full_asset_id, v.asset_nm, v.genre
HAVING COUNT(*) >= 5
ORDER BY avg_sat DESC
LIMIT 50;


-- =============================================================
-- 인덱스 사용률 통계 (테스트 실행 후)
-- =============================================================
\echo '--- 인덱스 사용률 ---'
SELECT
    indexrelname AS indexname,
    idx_scan        AS scans,
    idx_tup_read    AS tuples_read
FROM pg_stat_user_indexes
WHERE tablename IN ('user', 'vod', 'watch_history')
  AND idx_scan > 0
ORDER BY idx_scan DESC;
