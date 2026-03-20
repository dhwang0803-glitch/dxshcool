-- =============================================================
-- 장르별 인기 추천 테이블 DDL (Gold 계층)
-- 파일: Database_Design/schemas/create_popular_recommendation.sql
-- 목적: 장르별 Top-N 인기 추천 결과 저장 (글로벌, 비개인화)
-- 작성일: 2026-03-18
-- 배경:
--   serving.vod_recommendation은 유저 기반/콘텐츠 기반 개인화 추천 전용.
--   장르별 인기 추천은 기준 키(genre), 갱신 패턴(주 1회 일괄),
--   UNIQUE 제약(genre, rank)이 근본적으로 달라 별도 테이블로 분리.
--   다중 장르 VOD(드라마+영화)가 각 장르 Top-N에 중복 등장 가능.
-- 소비 브랜치: CF_Engine(쓰기), Vector_Search(쓰기), API_Server(읽기)
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_popular_recommendation.sql
-- 주의: serving 스키마가 먼저 생성되어야 함
-- =============================================================

CREATE TABLE serving.popular_recommendation (
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

-- API 쿼리 패턴: WHERE ct_cl = $1 ORDER BY rank LIMIT N
CREATE INDEX idx_popular_rec_ct_cl_rank
    ON serving.popular_recommendation (ct_cl, rank)
    INCLUDE (vod_id_fk, score, recommendation_type, expires_at);

-- TTL 만료 삭제용
CREATE INDEX idx_popular_rec_expires
    ON serving.popular_recommendation (expires_at);

-- updated_at 자동 갱신 트리거
CREATE TRIGGER trg_popular_rec_updated_at
    BEFORE UPDATE ON serving.popular_recommendation
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE serving.popular_recommendation IS
    '[Gold/Serving] CT_CL별 인기 추천 결과. 글로벌(비개인화) 랭킹. 주 1회 갱신, TTL 7일.';
COMMENT ON COLUMN serving.popular_recommendation.ct_cl IS
    'vod.ct_cl 값 (영화, TV드라마, TV애니메이션, TV 연예/오락 등). 고정 4개 카테고리 기준.';
COMMENT ON COLUMN serving.popular_recommendation.rank IS
    '장르 내 순위 (1부터 시작)';
COMMENT ON COLUMN serving.popular_recommendation.vod_id_fk IS
    'FK → vod.full_asset_id (ON DELETE CASCADE)';
COMMENT ON COLUMN serving.popular_recommendation.score IS
    'ML 스코어 (CF 시그널 + 인기도 + 신선도 등 조합, 0.0~1.0)';
COMMENT ON COLUMN serving.popular_recommendation.recommendation_type IS
    'POPULAR: 전체 인기 | TRENDING: 최근 급상승';
COMMENT ON COLUMN serving.popular_recommendation.updated_at IS
    '최종 갱신 시각 (트리거 자동). 주 1회 일괄 갱신 추적용.';
COMMENT ON COLUMN serving.popular_recommendation.expires_at IS
    'TTL 만료 시각 (기본 7일). db_maintenance.py에서 삭제.';
