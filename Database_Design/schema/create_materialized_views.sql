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
-- 생성 확인
-- =============================================================
SELECT
    matviewname,
    ispopulated,
    pg_size_pretty(pg_total_relation_size(matviewname::regclass)) AS total_size
FROM pg_matviews
WHERE matviewname IN ('mv_vod_satisfaction_stats', 'mv_age_grp_vod_stats')
ORDER BY matviewname;
