-- =============================================================
-- 마이그레이션: serving.popular_recommendation.genre → ct_cl 컬럼 변경
-- 파일: migrations/20260319_popular_rec_genre_to_ct_cl.sql
-- 작성일: 2026-03-19
-- 목적: 분류 기준을 vod.genre에서 vod.ct_cl로 변경
--        genre는 다중값(슬래시 구분)이라 집계 기준으로 부적절.
--        ct_cl은 단일 분류값으로 일관된 카테고리 분류 가능.
-- 영향 브랜치: Normal_Recommendation(쓰기), CF_Engine(쓰기), Vector_Search(쓰기), API_Server(읽기)
-- =============================================================

-- ─── UP ───

BEGIN;

-- 1. 기존 인덱스 삭제
DROP INDEX IF EXISTS serving.idx_popular_rec_genre_rank;

-- 2. 기존 UNIQUE 제약 삭제
ALTER TABLE serving.popular_recommendation
    DROP CONSTRAINT IF EXISTS uq_popular_genre_rank;

-- 3. 컬럼 이름 변경
ALTER TABLE serving.popular_recommendation
    RENAME COLUMN genre TO ct_cl;

-- 4. 새 UNIQUE 제약 추가
ALTER TABLE serving.popular_recommendation
    ADD CONSTRAINT uq_popular_ct_cl_rank UNIQUE (ct_cl, rank);

-- 5. 새 인덱스 생성
CREATE INDEX idx_popular_rec_ct_cl_rank
    ON serving.popular_recommendation (ct_cl, rank)
    INCLUDE (vod_id_fk, score, recommendation_type, expires_at);

-- 6. 컬럼 코멘트 갱신
COMMENT ON COLUMN serving.popular_recommendation.ct_cl IS
    'vod.ct_cl 값 (영화, TV드라마, TV애니메이션, TV 연예/오락 등). 고정 4개 카테고리 기준.';

COMMIT;

-- ─── DOWN (롤백) ───
-- BEGIN;
-- DROP INDEX IF EXISTS serving.idx_popular_rec_ct_cl_rank;
-- ALTER TABLE serving.popular_recommendation DROP CONSTRAINT IF EXISTS uq_popular_ct_cl_rank;
-- ALTER TABLE serving.popular_recommendation RENAME COLUMN ct_cl TO genre;
-- ALTER TABLE serving.popular_recommendation ADD CONSTRAINT uq_popular_genre_rank UNIQUE (genre, rank);
-- CREATE INDEX idx_popular_rec_genre_rank ON serving.popular_recommendation (genre, rank) INCLUDE (vod_id_fk, score, recommendation_type, expires_at);
-- COMMIT;
