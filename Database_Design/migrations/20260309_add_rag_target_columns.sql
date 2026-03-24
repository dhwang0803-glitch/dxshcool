-- =============================================================
-- Migration: add RAG target columns to vod table
-- Date: 2026-03-09
-- Branch: RAG
-- Purpose: RAG 파이프라인 타겟 컬럼 추가 (cast_lead, cast_guest, rating, release_date)
--
-- 적용 이력: RAG 브랜치 개발 중 직접 DB 적용됨 (마이그레이션 파일 사후 추가)
-- 현재 상태: 이미 DB에 적용 완료 (IF NOT EXISTS로 재실행 안전)
--
-- 컬럼별 NULL 현황 (2026-03-11 기준):
--   cast_lead:    72.0% 완성 (~46,444 NULL)
--   cast_guest:   53.0% 완성 (~78,075 NULL)
--   rating:       65.6% 완성 (~57,173 NULL)
--   release_date: 74.9% 완성 (~41,684 NULL)
-- =============================================================

BEGIN;

ALTER TABLE vod
    ADD COLUMN IF NOT EXISTS cast_lead   TEXT,
    ADD COLUMN IF NOT EXISTS cast_guest  TEXT,
    ADD COLUMN IF NOT EXISTS rating      VARCHAR(16),
    ADD COLUMN IF NOT EXISTS release_date DATE;

COMMENT ON COLUMN vod.cast_lead    IS '주연 배우 (RAG 파이프라인으로 수집, NULL = 미수집)';
COMMENT ON COLUMN vod.cast_guest   IS '게스트/조연 배우 (RAG 파이프라인으로 수집, NULL = 미수집)';
COMMENT ON COLUMN vod.rating       IS '관람등급 (전체관람가/12세이상/15세이상/18세이상 등, NULL = 미수집)';
COMMENT ON COLUMN vod.release_date IS '개봉/방영일 (DATE, NULL = 미수집)';

COMMIT;
