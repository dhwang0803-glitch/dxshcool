-- =============================================================
-- Migration: vod_embedding schema corrections
-- Date: 2026-03-08
-- Branch: VOD_Embedding
-- Purpose: vod_embedding 테이블 실제 DB 스키마와 파일 동기화
--
-- 변경 사항:
--   1. model_name VARCHAR(100) NOT NULL 컬럼 추가
--   2. vector_magnitude 타입 REAL → DOUBLE PRECISION 변경
--   3. created_at, updated_at NOT NULL 제약 추가
--
-- 적용 이력: VOD_Embedding 브랜치 개발 중 직접 DB 적용됨 (사후 추가)
-- 현재 상태: 이미 DB에 적용 완료 (IF NOT EXISTS / 조건부로 재실행 안전)
-- =============================================================

BEGIN;

-- [1] model_name 컬럼 추가 (없으면)
ALTER TABLE vod_embedding
    ADD COLUMN IF NOT EXISTS model_name VARCHAR(100) NOT NULL DEFAULT 'clip-ViT-B-32';

-- [2] vector_magnitude 타입 변경 REAL → DOUBLE PRECISION
--     이미 DOUBLE PRECISION이면 아래는 무시됨 (같은 타입이므로 오류 없음)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'vod_embedding'
          AND column_name = 'vector_magnitude'
          AND data_type = 'real'
    ) THEN
        ALTER TABLE vod_embedding
            ALTER COLUMN vector_magnitude TYPE DOUBLE PRECISION;
    END IF;
END $$;

-- [3] created_at, updated_at NOT NULL 제약 추가
--     NULL 값이 없을 때만 안전하게 적용됨 (파이럿 78건은 모두 now()로 채워짐)
ALTER TABLE vod_embedding
    ALTER COLUMN created_at SET NOT NULL,
    ALTER COLUMN updated_at SET NOT NULL;

COMMIT;
