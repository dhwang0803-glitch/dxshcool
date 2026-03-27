-- =============================================================
-- gen_rec_sentence 관련 테이블 DDL
-- 파일: Database_Design/schemas/create_rec_sentence.sql
-- 목적: VOD 감성 카피(rec_sentence) 서빙 인프라
--   1. serving.rec_sentence: VOD별 감성 문구 (홈 배너 포스터 하단)
-- 작성일: 2026-03-27
-- 소비 브랜치: gen_rec_sentence(쓰기), API_Server(읽기)
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_rec_sentence.sql
-- 주의: serving 스키마가 먼저 생성되어야 함 (20260312_create_serving_schema.sql)
-- =============================================================


-- =============================================================
-- 1. serving.rec_sentence: VOD 감성 카피
-- =============================================================
-- 특성:
--   - VOD당 1건 (유저 무관)
--   - CLIP 임베딩 + VOD 메타데이터 → LLM 생성
--   - API_Server가 홈 배너 응답에 포함하여 소비
--   - TTL 30일 (만료 후 batch_generate.py로 재생성)
-- =============================================================

CREATE TABLE serving.rec_sentence (
    vod_id_fk       VARCHAR(64)     NOT NULL
                        REFERENCES public.vod(full_asset_id) ON DELETE CASCADE,
    rec_sentence    TEXT            NOT NULL,
    embedding_used  BOOLEAN         NOT NULL DEFAULT FALSE,
    model_name      VARCHAR(100)    NOT NULL,
    generated_at    TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ     NOT NULL DEFAULT (NOW() + INTERVAL '30 days'),

    PRIMARY KEY (vod_id_fk),

    CONSTRAINT chk_rs_length CHECK (
        char_length(rec_sentence) BETWEEN 20 AND 120
    )
);

COMMENT ON TABLE serving.rec_sentence IS
    'VOD별 감성 카피. 홈 배너 포스터 하단 표시용. gen_rec_sentence 브랜치 생산.';
COMMENT ON COLUMN serving.rec_sentence.vod_id_fk IS
    'vod.full_asset_id FK. VOD당 1건 (유저 무관).';
COMMENT ON COLUMN serving.rec_sentence.rec_sentence IS
    '감성 문구 (2문장, 20~120자). 장면 시각화 + 기대감 형성 목적.';
COMMENT ON COLUMN serving.rec_sentence.embedding_used IS
    'CLIP 영상 임베딩을 LLM 입력에 포함했는지 여부.';
COMMENT ON COLUMN serving.rec_sentence.model_name IS
    '생성 모델명 (예: gemma2:9b, gemma2-rec:latest).';
COMMENT ON COLUMN serving.rec_sentence.expires_at IS
    'TTL 만료 시각. 만료된 행은 batch_generate.py가 재생성·UPSERT.';


-- =============================================================
-- 인덱스
-- =============================================================

-- API_Server: 만료 미포함 행 조회 최적화
CREATE INDEX idx_rec_sentence_expires
    ON serving.rec_sentence (expires_at)
    WHERE expires_at > NOW();

-- 모델별 통계 조회용
CREATE INDEX idx_rec_sentence_model
    ON serving.rec_sentence (model_name);


-- =============================================================
-- 테스터 격리용 미러 테이블 (is_test 유저 대상 A/B 테스트용)
-- =============================================================
-- 현재는 rec_sentence가 VOD당 1건(유저 무관)이므로 분리 불필요.
-- 향후 유저별 개인화 문구로 확장 시 _test 테이블 추가 검토.
