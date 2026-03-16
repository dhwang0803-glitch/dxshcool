-- =============================================================
-- Migration: serving.vod_recommendation에 source_vod_id 추가
-- 목적: Vector_Search 콘텐츠 기반 추천(VOD→VOD) 지원
--       기존 user_id_fk NOT NULL 제약이 콘텐츠 기반 추천과 충돌
-- 영향 브랜치: CF_Engine, Vector_Search, API_Server
-- 작성일: 2026-03-16
-- =============================================================
-- 배경:
--   유저 기반 추천: user_id_fk 필수, source_vod_id NULL
--   콘텐츠 기반 추천: user_id_fk NULL, source_vod_id 필수
--   → user_id_fk를 NULLABLE로 변경, source_vod_id 컬럼 추가
--   → CHECK 제약으로 둘 중 하나 필수 보장
-- =============================================================

BEGIN;

-- ---------------------------------------------------------
-- 1. user_id_fk: NOT NULL → NULLABLE
-- ---------------------------------------------------------
ALTER TABLE serving.vod_recommendation
    ALTER COLUMN user_id_fk DROP NOT NULL;

-- ---------------------------------------------------------
-- 2. source_vod_id 컬럼 추가 (콘텐츠 기반 추천의 기준 VOD)
-- ---------------------------------------------------------
ALTER TABLE serving.vod_recommendation
    ADD COLUMN source_vod_id VARCHAR(64);

ALTER TABLE serving.vod_recommendation
    ADD CONSTRAINT fk_vod_rec_source_vod
        FOREIGN KEY (source_vod_id) REFERENCES public.vod(full_asset_id) ON DELETE CASCADE;

COMMENT ON COLUMN serving.vod_recommendation.source_vod_id IS
    '콘텐츠 기반 추천 시 기준 VOD. 유저 기반 추천에서는 NULL.';

-- ---------------------------------------------------------
-- 3. CHECK 제약: user_id_fk 또는 source_vod_id 중 최소 하나 필수
-- ---------------------------------------------------------
ALTER TABLE serving.vod_recommendation
    ADD CONSTRAINT chk_rec_user_or_source
        CHECK (user_id_fk IS NOT NULL OR source_vod_id IS NOT NULL);

-- ---------------------------------------------------------
-- 4. recommendation_type에 CONTENT_BASED 추가
-- ---------------------------------------------------------
ALTER TABLE serving.vod_recommendation
    DROP CONSTRAINT chk_rec_type;

ALTER TABLE serving.vod_recommendation
    ADD CONSTRAINT chk_rec_type
        CHECK (recommendation_type IN (
            'VISUAL_SIMILARITY', 'COLLABORATIVE', 'HYBRID', 'CONTENT_BASED'
        ));

-- ---------------------------------------------------------
-- 5. UNIQUE 제약 재설계: 유저 기반 / 콘텐츠 기반 분리
--    PostgreSQL에서 NULL != NULL이므로 단일 UNIQUE로는 양쪽 커버 불가
-- ---------------------------------------------------------
ALTER TABLE serving.vod_recommendation
    DROP CONSTRAINT uq_vod_rec_user_vod;

-- 유저 기반: 동일 유저에게 같은 VOD 중복 추천 방지
CREATE UNIQUE INDEX uq_vod_rec_user_vod
    ON serving.vod_recommendation (user_id_fk, vod_id_fk)
    WHERE user_id_fk IS NOT NULL;

-- 콘텐츠 기반: 동일 기준 VOD에서 같은 VOD 중복 추천 방지
CREATE UNIQUE INDEX uq_vod_rec_source_vod
    ON serving.vod_recommendation (source_vod_id, vod_id_fk)
    WHERE source_vod_id IS NOT NULL;

-- ---------------------------------------------------------
-- 6. 커버링 인덱스 재생성 (source_vod_id 포함)
-- ---------------------------------------------------------
-- 기존 유저 기반 커버링 인덱스 교체
DROP INDEX IF EXISTS serving.idx_vod_rec_user_covering;

CREATE INDEX idx_vod_rec_user_covering
    ON serving.vod_recommendation (user_id_fk, rank)
    INCLUDE (vod_id_fk, score, recommendation_type, source_vod_id, expires_at)
    WHERE user_id_fk IS NOT NULL;

-- 콘텐츠 기반 커버링 인덱스 신규
-- 패턴: WHERE source_vod_id = $1 ORDER BY rank LIMIT N
CREATE INDEX idx_vod_rec_source_covering
    ON serving.vod_recommendation (source_vod_id, rank)
    INCLUDE (vod_id_fk, score, recommendation_type, expires_at)
    WHERE source_vod_id IS NOT NULL;

COMMIT;

-- =============================================================
-- DOWN (롤백)
-- =============================================================
-- BEGIN;
-- DROP INDEX IF EXISTS serving.idx_vod_rec_source_covering;
-- DROP INDEX IF EXISTS serving.idx_vod_rec_user_covering;
-- DROP INDEX IF EXISTS serving.uq_vod_rec_source_vod;
-- DROP INDEX IF EXISTS serving.uq_vod_rec_user_vod;
--
-- ALTER TABLE serving.vod_recommendation
--     ADD CONSTRAINT uq_vod_rec_user_vod UNIQUE (user_id_fk, vod_id_fk);
--
-- CREATE INDEX idx_vod_rec_user_covering
--     ON serving.vod_recommendation (user_id_fk, rank)
--     INCLUDE (vod_id_fk, score, recommendation_type, expires_at);
--
-- ALTER TABLE serving.vod_recommendation DROP CONSTRAINT chk_rec_type;
-- ALTER TABLE serving.vod_recommendation
--     ADD CONSTRAINT chk_rec_type
--         CHECK (recommendation_type IN ('VISUAL_SIMILARITY', 'COLLABORATIVE', 'HYBRID'));
--
-- ALTER TABLE serving.vod_recommendation DROP CONSTRAINT chk_rec_user_or_source;
-- ALTER TABLE serving.vod_recommendation DROP CONSTRAINT fk_vod_rec_source_vod;
-- ALTER TABLE serving.vod_recommendation DROP COLUMN source_vod_id;
-- ALTER TABLE serving.vod_recommendation ALTER COLUMN user_id_fk SET NOT NULL;
-- COMMIT;
