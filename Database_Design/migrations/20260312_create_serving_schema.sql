-- =============================================================
-- Migration: serving 스키마 생성 및 Gold 테이블 이전
-- 파일: migrations/20260312_create_serving_schema.sql
-- 작성일: 2026-03-12
-- =============================================================
-- 배경:
--   Bronze(로컬 Parquet) / Silver(public.*) / Gold(serving.*) 3계층 구조 도입.
--   API 서버가 바라보는 Gold 테이블을 serving 스키마로 분리하여
--   API 계정 권한을 serving으로 제한 가능하게 함.
--
-- 이전 대상 (Gold/Serving 계층):
--   public.vod_recommendation   → serving.vod_recommendation
--   public.mv_vod_watch_stats   → serving.mv_vod_watch_stats
--   public.mv_age_grp_vod_stats → serving.mv_age_grp_vod_stats
--   public.mv_daily_watch_stats → serving.mv_daily_watch_stats
--
-- Silver 계층 (public.*) 은 변경 없음:
--   public.vod, public."user", public.watch_history
--   public.vod_embedding, public.vod_meta_embedding, public.user_embedding
--
-- 영향받는 코드:
--   db_maintenance.py : MV 이름을 serving.mv_* 로 수정 (동일 커밋)
--   API_Server        : search_path = serving,public 설정 필요
--
-- 권한 설정 (API_Server 브랜치 착수 시 실행):
--   CREATE USER api_user WITH PASSWORD '...';
--   GRANT USAGE ON SCHEMA serving TO api_user;
--   GRANT SELECT ON ALL TABLES IN SCHEMA serving TO api_user;
--   GRANT USAGE ON SCHEMA public TO api_user;
--   GRANT SELECT ON public.vod, public."user" TO api_user;
-- =============================================================

BEGIN;

-- 1. serving 스키마 생성
CREATE SCHEMA IF NOT EXISTS serving;

-- 2. vod_recommendation 이전
--    FK(user, vod → public 테이블)는 cross-schema 참조로 유지됨
ALTER TABLE public.vod_recommendation SET SCHEMA serving;

-- 3. Materialized View 이전
ALTER MATERIALIZED VIEW public.mv_vod_watch_stats   SET SCHEMA serving;
ALTER MATERIALIZED VIEW public.mv_age_grp_vod_stats SET SCHEMA serving;
ALTER MATERIALIZED VIEW public.mv_daily_watch_stats SET SCHEMA serving;

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- ALTER TABLE serving.vod_recommendation SET SCHEMA public;
-- ALTER MATERIALIZED VIEW serving.mv_vod_watch_stats   SET SCHEMA public;
-- ALTER MATERIALIZED VIEW serving.mv_age_grp_vod_stats SET SCHEMA public;
-- ALTER MATERIALIZED VIEW serving.mv_daily_watch_stats SET SCHEMA public;
-- DROP SCHEMA IF EXISTS serving;
-- COMMIT;

-- =============================================================
-- 검증 쿼리
-- =============================================================
-- SELECT schemaname, tablename  FROM pg_tables    WHERE schemaname = 'serving';
-- SELECT schemaname, matviewname FROM pg_matviews  WHERE schemaname = 'serving';
