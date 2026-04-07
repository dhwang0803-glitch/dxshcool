-- ============================================================
-- 20260401_add_backdrop_url.sql
-- vod 테이블에 backdrop_url 컬럼 DDL 반영 (실제 DB에는 이미 존재)
-- ============================================================

-- UP
ALTER TABLE public.vod ADD COLUMN IF NOT EXISTS backdrop_url TEXT;

COMMENT ON COLUMN public.vod.backdrop_url IS 'TMDB backdrop 이미지 URL. 히어로 배너 배경용.';

-- DOWN
-- ALTER TABLE public.vod DROP COLUMN IF EXISTS backdrop_url;
