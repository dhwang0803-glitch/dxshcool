-- =============================================================
-- Migration: user_embedding 테이블 추가
-- 날짜: 2026-03-11
-- 목적: User_Embedding 브랜치의 사용자 행동 벡터 적재 대상 테이블 생성
-- 참조: PLAN_04_EXTENSION_TABLES.md, schemas/create_embedding_tables.sql
-- =============================================================
-- 선행 조건:
--   - create_tables.sql 완료 (user 테이블 존재)
--   - create_embedding_tables.sql 완료 (pgvector 확장, update_updated_at_column 함수 존재)
--   - vod_embedding 테이블 존재 (User_Embedding 파이프라인 실행 전 데이터 적재 필요)
-- =============================================================

-- user_embedding 테이블 생성
CREATE TABLE IF NOT EXISTS user_embedding (
    user_embedding_id   BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL UNIQUE,

    -- 벡터 데이터 (pgvector)
    embedding           VECTOR(512)     NOT NULL,

    -- 임베딩 메타데이터
    model_version       VARCHAR(64)     NOT NULL DEFAULT 'clip-ViT-B-32',

    -- 입력 데이터 품질
    vod_count           INTEGER         NOT NULL DEFAULT 0,
    vector_magnitude    DOUBLE PRECISION,

    -- 시간
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 제약
    CONSTRAINT fk_user_embedding_user
        FOREIGN KEY (user_id_fk) REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT chk_user_emb_vod_count
        CHECK (vod_count >= 0)
);

-- 벡터 유사도 인덱스 (데이터 적재 완료 후 별도 실행 권장)
-- lists = 500 : sqrt(242,702 사용자) ≈ 493 → 500
-- CREATE INDEX idx_user_emb_ivfflat
--     ON user_embedding
--     USING ivfflat (embedding vector_cosine_ops)
--     WITH (lists = 500);

-- 보조 인덱스
CREATE INDEX IF NOT EXISTS idx_user_emb_updated ON user_embedding (updated_at DESC);

-- updated_at 자동 갱신 트리거
CREATE TRIGGER trg_user_embedding_updated_at
    BEFORE UPDATE ON user_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 코멘트
COMMENT ON TABLE user_embedding IS
    '사용자 행동 기반 벡터 임베딩. watch_history의 시청 VOD에 대한 clip embedding 가중평균 (completion_rate 가중치). User_Embedding 브랜치 적재.';
COMMENT ON COLUMN user_embedding.embedding IS
    'watch_history × vod_embedding 가중평균 벡터. vod_embedding과 동일한 512차원 CLIP 공간. CF_Engine 학습 입력.';
COMMENT ON COLUMN user_embedding.vod_count IS
    '임베딩 생성에 사용된 고유 VOD 수. clip_embeddings가 존재하는 시청 이력만 포함.';
COMMENT ON COLUMN user_embedding.vector_magnitude IS
    'L2 norm. 1.0이면 정규화 완료 상태.';

-- 생성 확인
SELECT tablename
FROM pg_tables
WHERE tablename = 'user_embedding' AND schemaname = 'public';
