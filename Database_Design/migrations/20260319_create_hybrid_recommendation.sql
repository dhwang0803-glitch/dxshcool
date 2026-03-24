-- =============================================================
-- Migration: Hybrid_Layer 관련 테이블 4종 생성
-- 파일: migrations/20260319_create_hybrid_recommendation.sql
-- 작성일: 2026-03-19 (마이그레이션 보완: 2026-03-21)
-- =============================================================
-- 배경:
--   설명 가능한 추천(Explainable Recommendation) 인프라.
--   vod_tag: VOD 메타데이터 기반 해석 가능 태그
--   user_preference: 유저별 태그 선호 프로필
--   hybrid_recommendation: CF + Vector 리랭킹 + 설명 근거 포함 최종 추천
--   tag_recommendation: 유저 선호 태그별 VOD 추천 선반
--
-- 영향받는 브랜치:
--   Hybrid_Layer — 쓰기
--   API_Server   — 읽기
-- =============================================================

BEGIN;

-- 1. vod_tag
CREATE TABLE IF NOT EXISTS vod_tag (
    vod_id_fk       VARCHAR(64)  NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    tag_category    VARCHAR(32)  NOT NULL,
    tag_value       VARCHAR(100) NOT NULL,
    confidence      REAL         DEFAULT 1.0,
    PRIMARY KEY (vod_id_fk, tag_category, tag_value),

    CONSTRAINT chk_vt_category CHECK (tag_category IN (
        'director', 'actor', 'genre', 'genre_detail', 'rating'
    )),
    CONSTRAINT chk_vt_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_vt_category_value ON vod_tag(tag_category, tag_value);

COMMENT ON TABLE vod_tag IS
    'VOD 해석 가능 태그. 메타데이터(감독/배우/장르 등)에서 추출. Hybrid_Layer 설명 근거 생성에 사용.';

-- 2. user_preference
CREATE TABLE IF NOT EXISTS user_preference (
    user_id_fk      VARCHAR(64)  NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    tag_category    VARCHAR(32)  NOT NULL,
    tag_value       VARCHAR(100) NOT NULL,
    affinity        REAL         NOT NULL,
    watch_count     SMALLINT     NOT NULL,
    avg_completion  REAL,
    updated_at      TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (user_id_fk, tag_category, tag_value),

    CONSTRAINT chk_up_affinity    CHECK (affinity >= 0.0 AND affinity <= 1.0),
    CONSTRAINT chk_up_watch_count CHECK (watch_count >= 2),
    CONSTRAINT chk_up_completion  CHECK (avg_completion IS NULL OR (avg_completion >= 0.0 AND avg_completion <= 1.0))
);

CREATE INDEX IF NOT EXISTS idx_up_user_affinity ON user_preference(user_id_fk, affinity DESC);

COMMENT ON TABLE user_preference IS
    '유저별 태그 선호 프로필. watch_history × vod_tag 집계. Hybrid_Layer 리랭킹에 사용.';

-- 3. serving.hybrid_recommendation
CREATE TABLE IF NOT EXISTS serving.hybrid_recommendation (
    hybrid_rec_id       BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,
    rank                SMALLINT        NOT NULL,
    score               REAL            NOT NULL,
    explanation_tags    JSONB           NOT NULL,
    source_engines      VARCHAR(32)[]   NOT NULL,
    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '7 days',

    CONSTRAINT fk_hybrid_user
        FOREIGN KEY (user_id_fk) REFERENCES public."user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_hybrid_vod
        FOREIGN KEY (vod_id_fk) REFERENCES public.vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT uq_hybrid_user_vod   UNIQUE (user_id_fk, vod_id_fk),
    CONSTRAINT chk_hybrid_score     CHECK (score >= 0 AND score <= 1),
    CONSTRAINT chk_hybrid_rank      CHECK (rank >= 1)
);

CREATE INDEX IF NOT EXISTS idx_hybrid_user_rank
    ON serving.hybrid_recommendation (user_id_fk, rank)
    INCLUDE (vod_id_fk, score, explanation_tags, source_engines, expires_at);

CREATE INDEX IF NOT EXISTS idx_hybrid_expires
    ON serving.hybrid_recommendation (expires_at);

COMMENT ON TABLE serving.hybrid_recommendation IS
    '[Gold/Serving] 설명 가능한 최종 추천. CF_Engine + Vector_Search 후보를 vod_tag 기반 리랭킹. TTL 7일.';

-- 4. serving.tag_recommendation
CREATE TABLE IF NOT EXISTS serving.tag_recommendation (
    tag_rec_id          BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL,
    tag_category        VARCHAR(32)     NOT NULL,
    tag_value           VARCHAR(100)    NOT NULL,
    tag_rank            SMALLINT        NOT NULL,
    tag_affinity        REAL            NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,
    vod_rank            SMALLINT        NOT NULL,
    vod_score           REAL            NOT NULL,
    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '7 days',

    CONSTRAINT fk_tag_rec_user
        FOREIGN KEY (user_id_fk) REFERENCES public."user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_tag_rec_vod
        FOREIGN KEY (vod_id_fk) REFERENCES public.vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT uq_tag_rec_user_tag_vod UNIQUE (user_id_fk, tag_category, tag_value, vod_id_fk),
    CONSTRAINT chk_tag_rec_tag_rank    CHECK (tag_rank >= 1 AND tag_rank <= 5),
    CONSTRAINT chk_tag_rec_vod_rank    CHECK (vod_rank >= 1 AND vod_rank <= 10),
    CONSTRAINT chk_tag_rec_vod_score   CHECK (vod_score >= 0 AND vod_score <= 1),
    CONSTRAINT chk_tag_rec_affinity    CHECK (tag_affinity >= 0 AND tag_affinity <= 1)
);

CREATE INDEX IF NOT EXISTS idx_tag_rec_user_shelf
    ON serving.tag_recommendation (user_id_fk, tag_rank, vod_rank)
    INCLUDE (tag_category, tag_value, tag_affinity, vod_id_fk, vod_score, expires_at);

CREATE INDEX IF NOT EXISTS idx_tag_rec_expires
    ON serving.tag_recommendation (expires_at);

COMMENT ON TABLE serving.tag_recommendation IS
    '[Gold/Serving] 유저 선호 태그별 VOD 추천 선반. 태그 top 5 × VOD top 10. TTL 7일.';

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- DROP TABLE IF EXISTS serving.tag_recommendation;
-- DROP TABLE IF EXISTS serving.hybrid_recommendation;
-- DROP TABLE IF EXISTS user_preference;
-- DROP TABLE IF EXISTS vod_tag;
-- COMMIT;
