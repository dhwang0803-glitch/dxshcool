-- =============================================================
-- Migration: vod 테이블에 disp_rtm_min 컬럼 추가
-- 파일: migrations/20260314_add_disp_rtm_min_to_vod.sql
-- 작성일: 2026-03-14 (DDL 보완: 2026-03-21)
-- =============================================================
-- 배경:
--   disp_rtm_sec(초)를 분 단위로 변환한 값.
--   프론트엔드 VOD 상세 페이지에서 "00분" 표시용.
--   ROUND(disp_rtm_sec / 60) 산출.
--
-- 영향받는 브랜치:
--   API_Server — VOD 상세 응답에 분 단위 러닝타임 포함
-- =============================================================

BEGIN;

ALTER TABLE vod
    ADD COLUMN IF NOT EXISTS disp_rtm_min SMALLINT;

COMMENT ON COLUMN vod.disp_rtm_min IS '러닝타임 분 단위. ROUND(disp_rtm_sec / 60). 프론트엔드 표시용.';

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- ALTER TABLE vod DROP COLUMN IF EXISTS disp_rtm_min;
-- COMMIT;
