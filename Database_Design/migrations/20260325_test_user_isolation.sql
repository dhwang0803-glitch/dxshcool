-- ============================================================
-- Migration: 테스터 계정 완전 격리 (A + C 조합)
-- Date: 2026-03-25
-- Purpose: 테스터 12명의 합성 데이터가 CF_Engine 학습 행렬 및
--          Hybrid_Layer 집계를 오염시키지 않도록 분리
-- ============================================================

-- ── A. public."user".is_test 플래그 ─────────────────────────
ALTER TABLE public."user"
    ADD COLUMN IF NOT EXISTS is_test BOOLEAN NOT NULL DEFAULT FALSE;

-- 테스터 12명 마킹
UPDATE public."user"
SET is_test = TRUE
WHERE sha2_hash = ANY(ARRAY[
    -- C0 저관여
    'f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129', -- C0_저관여_50대
    '077eec56a021132c0ad3f7f94f1192d1821667258dfdcb00d9539a8f1bdfddc6', -- C0_저관여_60대
    -- C1 충성
    '248cfc7fd82301adabc3d917908bf84ddb6b662362c0994ddccfa53a666eba75', -- C1_충성_50대
    '877f7ce17f19e6e4503c13dc2b67e2e8b69d0830407cd53409a4907f25c7ee53', -- C1_충성_40대
    'b2bc828585a6060181456f48c66f4981f6b56e4d7a689c398dc814a2e757dfdf', -- C1_충성_30대
    'cf535eb5910e56c5e597fff165a6e6ecf6eb17c28bf30a3b77739787b4120f18', -- C1_충성_60대
    -- C2 헤비
    'da3da6ae52381ff5782832a3d908ce46057a5771d155dd690f2279b53455c79a', -- C2_헤비_50대
    '121aaaa7a282ea0074187319a5ae05d81e0d96bb8d9dea4d8b0bb462c72b3007', -- C2_헤비_40대
    'a8bfccc82c6059f29ec89d359b9f09b45ed131d81bffd3d008d428bf0e135d6e', -- C2_헤비_30대
    -- C3 키즈
    '0486b86e555429e746661fe3bb6b7f1b5aa57171bfdf06434777e0d359b36f1e', -- C3_키즈_40대
    'afcc0aa5c76c9db7f57d1e49877de0b6537c9cbf7b1c6fdc40d126a16ebaa4c0', -- C3_키즈_30대
    '1dcc3e37f935e439e95ee767f3873842872a6e9c68577e490a152f3f74bfff89'  -- C3_키즈_60대
]);

-- ── C. 테스트 전용 serving 테이블 3종 ────────────────────────

-- C-1. vod_recommendation_test (CF_Engine 테스트 결과)
CREATE TABLE IF NOT EXISTS serving.vod_recommendation_test (
    recommendation_id BIGSERIAL PRIMARY KEY,
    user_id_fk        VARCHAR(64),
    vod_id_fk         VARCHAR(64),
    rank              SMALLINT,
    score             REAL,
    recommendation_type VARCHAR(32),
    generated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at        TIMESTAMPTZ,
    source_vod_id     VARCHAR(64),
    UNIQUE (user_id_fk, vod_id_fk, recommendation_type)
);

COMMENT ON TABLE serving.vod_recommendation_test
    IS '테스터 전용 CF 추천 후보 — 본 serving.vod_recommendation 오염 방지용';

-- C-2. hybrid_recommendation_test (Hybrid_Layer 테스트 결과)
CREATE TABLE IF NOT EXISTS serving.hybrid_recommendation_test (
    hybrid_rec_id  BIGSERIAL PRIMARY KEY,
    user_id_fk     VARCHAR(64)  NOT NULL,
    vod_id_fk      VARCHAR(64)  NOT NULL,
    rank           SMALLINT,
    score          REAL,
    explanation_tags JSONB,
    source_engines   VARCHAR(32)[],
    generated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at     TIMESTAMPTZ,
    UNIQUE (user_id_fk, vod_id_fk)
);

COMMENT ON TABLE serving.hybrid_recommendation_test
    IS '테스터 전용 하이브리드 추천 — 본 serving.hybrid_recommendation 오염 방지용';

-- C-3. tag_recommendation_test (Phase 4 태그 선반 테스트 결과)
CREATE TABLE IF NOT EXISTS serving.tag_recommendation_test (
    tag_rec_id    BIGSERIAL PRIMARY KEY,
    user_id_fk    VARCHAR(64) NOT NULL,
    tag_category  VARCHAR(32),
    tag_value     VARCHAR(128),
    tag_rank      SMALLINT,
    tag_affinity  REAL,
    vod_id_fk     VARCHAR(64),
    vod_rank      SMALLINT,
    vod_score     REAL,
    generated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at    TIMESTAMPTZ
);

COMMENT ON TABLE serving.tag_recommendation_test
    IS '테스터 전용 태그 선반 추천 — 본 serving.tag_recommendation 오염 방지용';

-- ── 검증 쿼리 ────────────────────────────────────────────────
-- SELECT COUNT(*) FROM public."user" WHERE is_test = TRUE;   -- 기대값: 12
-- SELECT table_name FROM information_schema.tables
--   WHERE table_schema = 'serving' AND table_name LIKE '%_test';
