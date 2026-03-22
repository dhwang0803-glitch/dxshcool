-- =============================================================
-- Migration: serving.popular_recommendation 테이블 생성
-- 파일: migrations/20260318_create_popular_recommendation.sql
-- 작성일: 2026-03-18 (마이그레이션 이력 보완: 2026-03-21)
-- =============================================================
-- 배경:
--   CT_CL별 인기 Top-N 추천 결과 저장 (글로벌, 비개인화).
--   serving.vod_recommendation은 유저 기반/콘텐츠 기반 개인화 추천 전용.
--   인기 추천은 기준 키(ct_cl), 갱신 패턴(주 1회)이 근본적으로 달라 별도 테이블로 분리.
--
-- 참고:
--   이 테이블은 DDL(schemas/create_popular_recommendation.sql) 직접 실행으로
--   DB에 생성됨. 이 마이그레이션은 이력 보완 목적이며, IF NOT EXISTS로 안전.
--   이후 20260319_popular_rec_genre_to_ct_cl.sql에서 genre→ct_cl 컬럼 변경됨.
--
-- 영향받는 브랜치:
--   CF_Engine, Vector_Search — 쓰기
--   API_Server — 읽기
-- =============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS serving.popular_recommendation (
    popular_rec_id      BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ct_cl               VARCHAR(64)     NOT NULL,
    rank                SMALLINT        NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    score               REAL            NOT NULL,
    recommendation_type VARCHAR(32)     NOT NULL DEFAULT 'POPULAR',

    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '7 days',

    CONSTRAINT uq_popular_ct_cl_rank UNIQUE (ct_cl, rank),
    CONSTRAINT chk_popular_score     CHECK (score >= 0 AND score <= 1),
    CONSTRAINT chk_popular_rank      CHECK (rank >= 1),
    CONSTRAINT chk_popular_type      CHECK (recommendation_type IN ('POPULAR', 'TRENDING'))
);

CREATE INDEX IF NOT EXISTS idx_popular_rec_ct_cl_rank
    ON serving.popular_recommendation (ct_cl, rank)
    INCLUDE (vod_id_fk, score, recommendation_type, expires_at);

CREATE INDEX IF NOT EXISTS idx_popular_rec_expires
    ON serving.popular_recommendation (expires_at);

COMMENT ON TABLE serving.popular_recommendation IS
    '[Gold/Serving] CT_CL별 인기 추천 결과. 글로벌(비개인화) 랭킹. 주 1회 갱신, TTL 7일.';

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- DROP TABLE IF EXISTS serving.popular_recommendation;
-- COMMIT;
