-- =============================================================
-- Migration: vod 테이블에 disp_rtm_min (분 단위 러닝타임) 컬럼 추가
-- Date: 2026-03-20
-- Reason: Frontend에서 러닝타임을 숫자(분) 단위로 필요.
--         기존 disp_rtm(VARCHAR HH:MM) / disp_rtm_sec(INTEGER 초) 외에
--         분 단위 SMALLINT 컬럼 추가.
-- Depends: disp_rtm_sec 컬럼 (이미 존재)
-- Consumers: API_Server (GET /vod/{series_nm} 응답에 disp_rtm_min 포함)
-- =============================================================

-- UP
ALTER TABLE public.vod
    ADD COLUMN IF NOT EXISTS disp_rtm_min SMALLINT;

COMMENT ON COLUMN vod.disp_rtm_min IS '상영시간 분 단위 변환값 (disp_rtm_sec / 60 반올림). Frontend 응답용.';

-- Backfill: disp_rtm_sec → 분 단위 변환
UPDATE public.vod
SET    disp_rtm_min = ROUND(disp_rtm_sec / 60.0)::SMALLINT
WHERE  disp_rtm_sec IS NOT NULL
  AND  disp_rtm_min IS NULL;

-- =============================================================
-- DOWN (롤백용)
-- ALTER TABLE public.vod DROP COLUMN IF EXISTS disp_rtm_min;
-- =============================================================
