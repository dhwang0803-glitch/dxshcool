-- =============================================================
-- Phase 3B OPT-2: Materialized View 생성
-- 파일: Database_Design/schema/create_materialized_views.sql
-- 작성일: 2026-03-07
-- 참조: PLAN_03B_PERFORMANCE_OPT.md
-- =============================================================
-- 목적: P04(만족도 상위 VOD), P06(연령대별 선호 VOD) 집계를 사전 계산
--       원본 쿼리 대비 <10ms 응답 목표
-- 주의: 초기 생성 시 원본 쿼리 수준의 시간 소요 (20~40분 예상)
--       REFRESH CONCURRENTLY는 UNIQUE INDEX 필수
--       일 1회 REFRESH 권장: REFRESH MATERIALIZED VIEW CONCURRENTLY mv_name;
-- =============================================================


-- =============================================================
-- [OPT-2-A] mv_vod_satisfaction_stats: P04 대체
-- 목적: 만족도 상위 VOD 집계 사전 계산
-- 원본: satisfaction > 0인 2.98M rows 전체 집계 (22,201ms cold)
-- =============================================================
CREATE MATERIALIZED VIEW mv_vod_satisfaction_stats AS
SELECT
    v.full_asset_id,
    v.asset_nm,
    v.genre,
    v.ct_cl,
    COUNT(wh.watch_history_id)  AS view_count,
    AVG(wh.satisfaction)        AS avg_satisfaction
FROM vod v
JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
WHERE wh.satisfaction > 0
GROUP BY v.full_asset_id, v.asset_nm, v.genre, v.ct_cl
HAVING COUNT(wh.watch_history_id) >= 10;

-- CONCURRENTLY REFRESH를 위한 UNIQUE INDEX (필수)
CREATE UNIQUE INDEX ON mv_vod_satisfaction_stats (full_asset_id);

-- 조회 최적화 인덱스
CREATE INDEX ON mv_vod_satisfaction_stats (avg_satisfaction DESC);


-- =============================================================
-- [OPT-2-B] mv_age_grp_vod_stats: P06 대체
-- 목적: 연령대별 VOD 선호도 집계 사전 계산
-- 원본: user JOIN watch_history JOIN vod 3-table (10,355ms warm)
-- =============================================================
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

-- CONCURRENTLY REFRESH를 위한 UNIQUE INDEX (필수)
CREATE UNIQUE INDEX ON mv_age_grp_vod_stats (age_grp10, full_asset_id);

-- 조회 최적화 인덱스
CREATE INDEX ON mv_age_grp_vod_stats (age_grp10, avg_satisfaction DESC);


-- =============================================================
-- [OPT-3-A] mv_vod_watch_stats: P02 대체
-- 목적: VOD별 전체 시청 통계 사전 집계 — 유저 대시보드 최다 조회수 배너 용도
-- 원본: WHERE vod_id_fk = '최다시청VOD' → 71,672건 Bitmap Heap Scan (1,714ms warm)
-- 참조: PLAN_03C_PARTITIONING_ANALYSIS.md
-- 작성일: 2026-03-08
-- 주의: 파티셔닝 후 원본 P02 쿼리는 전체 파티션 스캔으로 오히려 느려질 수 있음
--       → MV 조회로 대체하여 <1ms 목표
-- =============================================================
CREATE MATERIALIZED VIEW mv_vod_watch_stats AS
SELECT
    wh.vod_id_fk,
    v.asset_nm,
    v.genre,
    v.ct_cl,
    COUNT(*)                        AS total_views,
    COUNT(DISTINCT wh.user_id_fk)   AS unique_viewers,
    AVG(wh.completion_rate)         AS avg_completion,
    AVG(wh.satisfaction)            AS avg_satisfaction,
    MAX(wh.strt_dt)                 AS last_viewed
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
GROUP BY wh.vod_id_fk, v.asset_nm, v.genre, v.ct_cl;

-- CONCURRENTLY REFRESH를 위한 UNIQUE INDEX (필수)
CREATE UNIQUE INDEX ON mv_vod_watch_stats (vod_id_fk);

-- 대시보드 배너: 최다 조회수 기준 정렬 인덱스
CREATE INDEX ON mv_vod_watch_stats (total_views DESC);

-- 만족도 기준 정렬 인덱스 (P04 보완)
CREATE INDEX ON mv_vod_watch_stats (avg_satisfaction DESC);


-- =============================================================
-- [OPT-3-B] mv_daily_watch_stats: P03 대체
-- 목적: 날짜 범위 집계를 일별 사전 계산 → 기간 쿼리 시 row 수 최대 31개
-- 원본: 1주 범위 787K rows 집계 (15,315ms warm) → MV는 7행 집계 (<1ms)
-- 주의: COUNT(DISTINCT user_id_fk)는 일별 기준 → 주간 중복 제거 불가 (근사치)
--       정확한 주간 DAU가 필요하면 원본 쿼리 + 파티셔닝 조합 사용
-- =============================================================
CREATE MATERIALIZED VIEW mv_daily_watch_stats AS
SELECT
    DATE(strt_dt AT TIME ZONE 'UTC')    AS watch_date,
    COUNT(*)                            AS total_views,
    COUNT(DISTINCT user_id_fk)          AS daily_active_users,
    AVG(completion_rate)                AS avg_completion,
    AVG(satisfaction)                   AS avg_satisfaction
FROM watch_history
GROUP BY DATE(strt_dt AT TIME ZONE 'UTC');

-- CONCURRENTLY REFRESH를 위한 UNIQUE INDEX (필수)
CREATE UNIQUE INDEX ON mv_daily_watch_stats (watch_date);

-- 날짜 범위 조회 인덱스
CREATE INDEX ON mv_daily_watch_stats (watch_date DESC);


-- =============================================================
-- 전체 MV 생성 확인
-- =============================================================
SELECT
    matviewname,
    ispopulated,
    pg_size_pretty(pg_total_relation_size(matviewname::regclass)) AS total_size
FROM pg_matviews
WHERE matviewname IN (
    'mv_vod_satisfaction_stats',
    'mv_age_grp_vod_stats',
    'mv_vod_watch_stats',
    'mv_daily_watch_stats'
)
ORDER BY matviewname;
