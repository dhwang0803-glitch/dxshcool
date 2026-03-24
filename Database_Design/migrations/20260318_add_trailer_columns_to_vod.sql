-- =============================================================
-- Migration: vod 테이블에 트레일러 관련 컬럼 3개 추가
-- 파일: migrations/20260318_add_trailer_columns_to_vod.sql
-- 작성일: 2026-03-18
-- =============================================================
-- 배경:
--   Object_Detection 파이프라인이 트레일러 영상을 분석하기 위해
--   YouTube 영상 ID, 영상 길이, 처리 완료 플래그가 필요.
--
-- 추가 컬럼:
--   youtube_video_id   VARCHAR(20)   — YouTube iframe 재생용
--   duration_sec       REAL          — 영상 길이 (초)
--   trailer_processed  BOOLEAN       — Object_Detection 처리 완료 여부
--
-- 영향받는 브랜치:
--   Object_Detection — youtube_video_id로 트레일러 다운로드, trailer_processed 플래그 갱신
--   Shopping_Ad      — duration_sec 참조 가능
-- =============================================================

BEGIN;

ALTER TABLE vod
    ADD COLUMN IF NOT EXISTS youtube_video_id  VARCHAR(20),
    ADD COLUMN IF NOT EXISTS duration_sec      REAL,
    ADD COLUMN IF NOT EXISTS trailer_processed BOOLEAN DEFAULT FALSE;

-- 미처리 VOD 필터링용 부분 인덱스
CREATE INDEX IF NOT EXISTS idx_vod_trailer_unprocessed
    ON vod(full_asset_id)
    WHERE trailer_processed = FALSE OR trailer_processed IS NULL;

COMMENT ON COLUMN vod.youtube_video_id  IS 'YouTube 영상 ID (iframe 재생용). Object_Detection 트레일러 다운로드 입력.';
COMMENT ON COLUMN vod.duration_sec      IS '영상 길이 (초). 트레일러 또는 본편.';
COMMENT ON COLUMN vod.trailer_processed IS 'Object_Detection 파이프라인 처리 완료 여부 (FALSE/NULL = 미처리)';

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- DROP INDEX IF EXISTS idx_vod_trailer_unprocessed;
-- ALTER TABLE vod
--     DROP COLUMN IF EXISTS youtube_video_id,
--     DROP COLUMN IF EXISTS duration_sec,
--     DROP COLUMN IF EXISTS trailer_processed;
-- COMMIT;

-- =============================================================
-- 검증 쿼리
-- =============================================================
-- SELECT column_name, data_type, column_default
-- FROM information_schema.columns
-- WHERE table_name = 'vod'
--   AND column_name IN ('youtube_video_id', 'duration_sec', 'trailer_processed');
