-- =============================================================
-- Migration: mv_vod_satisfaction_stats 제거 + MV 인덱스 보완
-- 파일: migrations/20260312_mv_cleanup_and_indexes.sql
-- 작성일: 2026-03-12
-- 배경:
--   mv_vod_satisfaction_stats(P04)가 mv_vod_watch_stats와 중복.
--   mv_vod_watch_stats는 avg_satisfaction, total_views, unique_viewers,
--   avg_completion, last_viewed를 모두 포함하므로 P04 쿼리를
--   동일하게 처리 가능. REFRESH 비용 절감을 위해 제거.
--
--   추가로 API 필터 패턴(장르별, 연령대별 조회수)에 대응하는
--   인덱스를 mv_vod_watch_stats, mv_age_grp_vod_stats에 추가.
--
-- REFRESH 영향:
--   db_maintenance.py: MATERIALIZED_VIEWS 목록에서 제거 완료.
--   mv_vod_watch_stats가 P02+P04 역할 통합 담당.
-- =============================================================

-- =============================================================
-- [1] mv_vod_satisfaction_stats 제거
--     주의: DROP은 비가역적. 검증 후 실행.
-- =============================================================

-- 사전 확인: mv_vod_watch_stats가 동일 쿼리를 처리할 수 있는지 확인
-- SELECT COUNT(*) FROM mv_vod_watch_stats WHERE avg_satisfaction > 0;
-- → 0보다 크면 P04 대체 가능 확인됨

DROP MATERIALIZED VIEW IF EXISTS mv_vod_satisfaction_stats;


-- =============================================================
-- [2] mv_vod_watch_stats 인덱스 보완
--     장르/콘텐츠 타입별 필터 패턴 대응
-- =============================================================

-- 장르별 인기 콘텐츠 (WHERE genre = $1 ORDER BY total_views DESC)
CREATE INDEX IF NOT EXISTS idx_mv_vws_genre_views
    ON mv_vod_watch_stats (genre, total_views DESC);

-- 콘텐츠 타입별 만족도 정렬 (WHERE ct_cl = $1 ORDER BY avg_satisfaction DESC)
CREATE INDEX IF NOT EXISTS idx_mv_vws_ctcl_satisfaction
    ON mv_vod_watch_stats (ct_cl, avg_satisfaction DESC);


-- =============================================================
-- [3] mv_age_grp_vod_stats 인덱스 보완
--     조회수 기준 정렬 패턴 추가 (기존: avg_satisfaction만 있음)
-- =============================================================

-- 연령대별 조회수 정렬 (WHERE age_grp10 = $1 ORDER BY view_count DESC)
CREATE INDEX IF NOT EXISTS idx_mv_agvs_age_views
    ON mv_age_grp_vod_stats (age_grp10, view_count DESC);


-- =============================================================
-- 롤백 (필요 시 — mv_vod_satisfaction_stats 재생성)
-- =============================================================
-- DROP INDEX IF EXISTS idx_mv_vws_genre_views;
-- DROP INDEX IF EXISTS idx_mv_vws_ctcl_satisfaction;
-- DROP INDEX IF EXISTS idx_mv_agvs_age_views;
--
-- CREATE MATERIALIZED VIEW mv_vod_satisfaction_stats AS
-- SELECT
--     v.full_asset_id, v.asset_nm, v.genre, v.ct_cl,
--     COUNT(wh.watch_history_id) AS view_count,
--     AVG(wh.satisfaction)       AS avg_satisfaction
-- FROM vod v
-- JOIN watch_history wh ON v.full_asset_id = wh.vod_id_fk
-- WHERE wh.satisfaction > 0
-- GROUP BY v.full_asset_id, v.asset_nm, v.genre, v.ct_cl
-- HAVING COUNT(wh.watch_history_id) >= 10;
-- CREATE UNIQUE INDEX ON mv_vod_satisfaction_stats (full_asset_id);
-- CREATE INDEX ON mv_vod_satisfaction_stats (avg_satisfaction DESC);

-- =============================================================
-- 검증 쿼리
-- =============================================================
-- MV 목록 확인 (mv_vod_satisfaction_stats 없어야 함)
-- SELECT matviewname FROM pg_matviews ORDER BY matviewname;

-- 신규 인덱스 확인
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename IN ('mv_vod_watch_stats', 'mv_age_grp_vod_stats')
-- ORDER BY tablename, indexname;
