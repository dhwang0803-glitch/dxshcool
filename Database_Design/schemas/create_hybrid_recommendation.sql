-- =============================================================
-- Hybrid_Layer 관련 테이블 DDL
-- 파일: Database_Design/schemas/create_hybrid_recommendation.sql
-- 목적: 설명 가능한 추천(Explainable Recommendation) 인프라
--   1. vod_tag: VOD 해석 가능 태그 (메타데이터 기반)
--   2. user_preference: 유저별 태그 선호 프로필
--   3. serving.hybrid_recommendation: 최종 리랭킹 + 설명 근거 포함 추천
--   4. serving.tag_recommendation: 유저 선호 태그별 VOD 추천 (태그 선반)
-- 작성일: 2026-03-19
-- 소비 브랜치: Hybrid_Layer(쓰기), API_Server(읽기)
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_hybrid_recommendation.sql
-- 주의: serving 스키마가 먼저 생성되어야 함 (20260312_create_serving_schema.sql)
-- =============================================================


-- =============================================================
-- 1. vod_tag: VOD 해석 가능 태그
-- =============================================================

CREATE TABLE vod_tag (
    vod_id_fk       VARCHAR(64)  NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    tag_category    VARCHAR(32)  NOT NULL,
    tag_value       VARCHAR(100) NOT NULL,
    confidence      REAL         DEFAULT 1.0,
    PRIMARY KEY (vod_id_fk, tag_category, tag_value),

    CONSTRAINT chk_vt_category CHECK (tag_category IN (
        'director', 'actor_lead', 'actor_guest', 'genre', 'genre_detail', 'rating'
    )),
    CONSTRAINT chk_vt_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0)
);

CREATE INDEX idx_vt_category_value ON vod_tag(tag_category, tag_value);

COMMENT ON TABLE vod_tag IS
    'VOD 해석 가능 태그. 메타데이터(감독/배우/장르 등)에서 추출. Hybrid_Layer 설명 근거 생성에 사용.';
COMMENT ON COLUMN vod_tag.vod_id_fk    IS 'FK → vod.full_asset_id (ON DELETE CASCADE)';
COMMENT ON COLUMN vod_tag.tag_category IS '태그 카테고리: director, actor_lead, actor_guest, genre, genre_detail, rating';
COMMENT ON COLUMN vod_tag.tag_value    IS '태그 값: 감독명, 배우명, 장르명 등';
COMMENT ON COLUMN vod_tag.confidence   IS '태그 신뢰도 (메타데이터 기반 = 1.0)';


-- =============================================================
-- 2. user_preference: 유저별 태그 선호 프로필
-- =============================================================

CREATE TABLE user_preference (
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

CREATE INDEX idx_up_user_affinity ON user_preference(user_id_fk, affinity DESC);

COMMENT ON TABLE user_preference IS
    '유저별 태그 선호 프로필. watch_history × vod_tag 집계. Hybrid_Layer 리랭킹에 사용.';
COMMENT ON COLUMN user_preference.user_id_fk    IS 'FK → user.sha2_hash (ON DELETE CASCADE)';
COMMENT ON COLUMN user_preference.tag_category  IS '태그 카테고리 (vod_tag.tag_category와 동일)';
COMMENT ON COLUMN user_preference.tag_value     IS '태그 값';
COMMENT ON COLUMN user_preference.affinity      IS '선호 강도 (0.0~1.0). 시청빈도 × 완주율 정규화';
COMMENT ON COLUMN user_preference.watch_count   IS '해당 태그 VOD 시청 횟수 (최소 2회 이상)';
COMMENT ON COLUMN user_preference.avg_completion IS '해당 태그 VOD 평균 완주율';
COMMENT ON COLUMN user_preference.updated_at    IS '최종 갱신 시각';


-- =============================================================
-- 3. serving.hybrid_recommendation: 최종 설명 가능 추천
-- =============================================================

CREATE TABLE serving.hybrid_recommendation (
    hybrid_rec_id       BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,
    rank                SMALLINT        NOT NULL,
    score               REAL            NOT NULL,

    -- 설명 근거: [{"category":"director","value":"봉준호","affinity":0.92}, ...]
    explanation_tags    JSONB           NOT NULL,

    -- 출처 엔진: ARRAY['COLLABORATIVE','VISUAL_SIMILARITY'] 등
    source_engines      VARCHAR(32)[]   NOT NULL,

    -- TTL 관리
    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '7 days',

    -- FK
    CONSTRAINT fk_hybrid_user
        FOREIGN KEY (user_id_fk) REFERENCES public."user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_hybrid_vod
        FOREIGN KEY (vod_id_fk) REFERENCES public.vod(full_asset_id) ON DELETE CASCADE,

    -- 제약
    CONSTRAINT uq_hybrid_user_vod   UNIQUE (user_id_fk, vod_id_fk),
    CONSTRAINT chk_hybrid_score     CHECK (score >= 0 AND score <= 1),
    CONSTRAINT chk_hybrid_rank      CHECK (rank >= 1)
);

-- API 쿼리: WHERE user_id_fk = $1 ORDER BY rank LIMIT 20
CREATE INDEX idx_hybrid_user_rank
    ON serving.hybrid_recommendation (user_id_fk, rank)
    INCLUDE (vod_id_fk, score, explanation_tags, source_engines, expires_at);

-- TTL 만료 삭제용
CREATE INDEX idx_hybrid_expires
    ON serving.hybrid_recommendation (expires_at);

COMMENT ON TABLE serving.hybrid_recommendation IS
    '[Gold/Serving] 설명 가능한 최종 추천. CF_Engine + Vector_Search 후보를 vod_tag 기반 리랭킹. TTL 7일.';
COMMENT ON COLUMN serving.hybrid_recommendation.explanation_tags IS
    'JSONB 배열. 추천 근거 태그 (category, value, affinity). 프론트엔드 표시용.';
COMMENT ON COLUMN serving.hybrid_recommendation.source_engines IS
    '추천 출처 엔진 배열. COLLABORATIVE, VISUAL_SIMILARITY, CONTENT_BASED 등.';
COMMENT ON COLUMN serving.hybrid_recommendation.expires_at IS
    'TTL 만료 시각 (기본 7일). db_maintenance.py에서 삭제.';


-- =============================================================
-- 4. serving.tag_recommendation: 유저 선호 태그별 VOD 추천
-- =============================================================
-- 용도: 프론트엔드에서 "봉준호 감독 작품", "드라마 장르" 등 선반(shelf) 표시
-- 구조: 유저 × 선호 태그(top 5) × 태그별 VOD(top 10)
-- 쿼리 패턴: GET /recommendations/{user_id}/tags
--   → 유저의 선호 태그 5개 + 태그별 VOD 10개 = 최대 50건

CREATE TABLE serving.tag_recommendation (
    tag_rec_id          BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL,
    tag_category        VARCHAR(32)     NOT NULL,
    tag_value           VARCHAR(100)    NOT NULL,
    tag_rank            SMALLINT        NOT NULL,   -- 유저 선호 태그 순위 (1~5)
    tag_affinity        REAL            NOT NULL,   -- user_preference.affinity 복사

    vod_id_fk           VARCHAR(64)     NOT NULL,
    vod_rank            SMALLINT        NOT NULL,   -- 태그 내 VOD 순위 (1~10)
    vod_score           REAL            NOT NULL,   -- 랭킹 점수 (인기도/신선도/평점 조합)

    -- TTL 관리
    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '7 days',

    -- FK
    CONSTRAINT fk_tag_rec_user
        FOREIGN KEY (user_id_fk) REFERENCES public."user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_tag_rec_vod
        FOREIGN KEY (vod_id_fk) REFERENCES public.vod(full_asset_id) ON DELETE CASCADE,

    -- 제약
    CONSTRAINT uq_tag_rec_user_tag_vod UNIQUE (user_id_fk, tag_category, tag_value, vod_id_fk),
    CONSTRAINT chk_tag_rec_tag_rank    CHECK (tag_rank >= 1 AND tag_rank <= 5),
    CONSTRAINT chk_tag_rec_vod_rank    CHECK (vod_rank >= 1 AND vod_rank <= 10),
    CONSTRAINT chk_tag_rec_vod_score   CHECK (vod_score >= 0 AND vod_score <= 1),
    CONSTRAINT chk_tag_rec_affinity    CHECK (tag_affinity >= 0 AND tag_affinity <= 1)
);

-- API 쿼리: WHERE user_id_fk = $1 ORDER BY tag_rank, vod_rank
CREATE INDEX idx_tag_rec_user_shelf
    ON serving.tag_recommendation (user_id_fk, tag_rank, vod_rank)
    INCLUDE (tag_category, tag_value, tag_affinity, vod_id_fk, vod_score, expires_at);

-- TTL 만료 삭제용
CREATE INDEX idx_tag_rec_expires
    ON serving.tag_recommendation (expires_at);

COMMENT ON TABLE serving.tag_recommendation IS
    '[Gold/Serving] 유저 선호 태그별 VOD 추천 선반. 태그 top 5 × VOD top 10. TTL 7일.';
COMMENT ON COLUMN serving.tag_recommendation.tag_category IS '선호 태그 카테고리 (director, actor_lead, actor_guest, genre, genre_detail, rating)';
COMMENT ON COLUMN serving.tag_recommendation.tag_value    IS '선호 태그 값 (봉준호, 송강호, 드라마 등)';
COMMENT ON COLUMN serving.tag_recommendation.tag_rank     IS '유저 선호 태그 순위 (1=최선호, 최대 5)';
COMMENT ON COLUMN serving.tag_recommendation.tag_affinity IS '유저의 해당 태그 선호 강도 (user_preference.affinity)';
COMMENT ON COLUMN serving.tag_recommendation.vod_id_fk    IS 'FK → vod.full_asset_id. 해당 태그 관련 추천 VOD';
COMMENT ON COLUMN serving.tag_recommendation.vod_rank     IS '태그 내 VOD 순위 (1=최상위, 최대 10)';
COMMENT ON COLUMN serving.tag_recommendation.vod_score    IS 'VOD 랭킹 점수 (인기도/신선도/평점 조합, 0.0~1.0)';
COMMENT ON COLUMN serving.tag_recommendation.expires_at   IS 'TTL 만료 시각 (기본 7일). db_maintenance.py에서 삭제.';
