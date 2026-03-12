-- =============================================================
-- Migration: embedding_type 'VISUAL' → 'CLIP' 통일
-- 파일: migrations/20260312_fix_embedding_type_clip.sql
-- 작성일: 2026-03-12
-- 배경:
--   create_embedding_tables.sql의 chk_embedding_type CHECK 제약과
--   vod_ingest_pipeline.py의 EMBEDDING_TYPE 상수가 'VISUAL'을 사용.
--   그러나 VOD_Embedding 브랜치(CLAUDE.md) 및 User_Embedding 브랜치(PLAN_02)는
--   'CLIP'을 표준 값으로 사용함. 브랜치 간 불일치를 'CLIP'으로 통일.
-- 영향:
--   - vod_embedding.chk_embedding_type: 'VISUAL' 제거 → 'CLIP' 추가
--   - 기존 'VISUAL' 데이터가 있으면 'CLIP'으로 일괄 변환
--   - VOD_Embedding 브랜치: ingest_to_db.py 작성 시 embedding_type='CLIP' 사용
--   - User_Embedding 브랜치: PLAN_02 쿼리와 정합성 확보
-- =============================================================

BEGIN;

-- 1. 기존 데이터 변환: VISUAL → CLIP (데이터가 없으면 영향 없음)
UPDATE vod_embedding
SET embedding_type = 'CLIP'
WHERE embedding_type = 'VISUAL';

-- 2. 기존 CHECK 제약 제거
ALTER TABLE vod_embedding
    DROP CONSTRAINT IF EXISTS chk_embedding_type;

-- 3. 새 CHECK 제약 추가 ('CLIP' 기준)
ALTER TABLE vod_embedding
    ADD CONSTRAINT chk_embedding_type
        CHECK (embedding_type IN ('CLIP', 'CONTENT', 'HYBRID'));

-- 4. DEFAULT 값도 변경
ALTER TABLE vod_embedding
    ALTER COLUMN embedding_type SET DEFAULT 'CLIP';

COMMIT;

-- =============================================================
-- 검증 쿼리 (마이그레이션 후 실행)
-- =============================================================
-- VISUAL 잔존 여부 확인 (0 이어야 함)
-- SELECT COUNT(*) FROM vod_embedding WHERE embedding_type = 'VISUAL';

-- CHECK 제약 확인
-- SELECT conname, pg_get_constraintdef(oid)
-- FROM pg_constraint
-- WHERE conrelid = 'vod_embedding'::regclass AND conname = 'chk_embedding_type';
