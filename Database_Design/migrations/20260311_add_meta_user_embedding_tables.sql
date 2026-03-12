-- =============================================================
-- Migration: vod_meta_embedding + user_embedding 테이블 추가
-- 날짜: 2026-03-11
-- 배경: VOD 메타데이터 임베딩(384차원) + User 임베딩(896차원) 저장
-- =============================================================
-- 실행 전 확인:
--   1. pgvector 확장 설치 여부: SELECT * FROM pg_extension WHERE extname = 'vector';
--   2. update_updated_at_column() 함수 존재 여부 (create_embedding_tables.sql 실행 완료)
--   3. vod.full_asset_id, "user".sha2_hash 컬럼 존재 여부
-- =============================================================

BEGIN;

-- ── [1] vod_meta_embedding ────────────────────────────────────

CREATE TABLE IF NOT EXISTS vod_meta_embedding (
    vod_meta_emb_id     BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL UNIQUE,
    embedding           VECTOR(384)     NOT NULL,
    input_text          TEXT,
    source_fields       TEXT[]          NOT NULL
                            DEFAULT ARRAY['asset_nm','genre','director','cast_lead','smry'],
    model_name          VARCHAR(100)    NOT NULL
                            DEFAULT 'paraphrase-multilingual-MiniLM-L12-v2',
    embedding_dim       SMALLINT        NOT NULL DEFAULT 384,
    vector_magnitude    DOUBLE PRECISION,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT fk_vod_meta_emb_vod
        FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT chk_meta_emb_dim
        CHECK (embedding_dim > 0)
);

CREATE INDEX IF NOT EXISTS idx_vod_meta_emb_ivfflat
    ON vod_meta_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 400);

CREATE INDEX IF NOT EXISTS idx_vod_meta_emb_updated
    ON vod_meta_embedding (updated_at DESC);

CREATE TRIGGER trg_vod_meta_emb_updated_at
    BEFORE UPDATE ON vod_meta_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ── [2] user_embedding ───────────────────────────────────────
-- 생성 브랜치: User_Embedding (가중평균 벡터)
-- ALS 관련 컬럼(factors/iterations/train_loss)은 CF_Engine 브랜치에서 ALTER TABLE로 추가

CREATE TABLE IF NOT EXISTS user_embedding (
    user_emb_id         BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL UNIQUE,

    -- 벡터 (896차원 = CLIP 512 + paraphrase-multilingual 384, L2 정규화 후 concat)
    embedding           VECTOR(896)     NOT NULL,

    -- 생성 방식
    model_name          VARCHAR(100)    NOT NULL DEFAULT 'weighted_mean',
    -- weighted_mean: completion_rate 가중 평균 (User_Embedding 브랜치)
    -- ALS: 행렬 분해 정제 (CF_Engine 브랜치 — 추후 컬럼 추가)

    -- 입력 품질
    vod_count           INTEGER         NOT NULL DEFAULT 0,
    -- 임베딩 생성에 사용된 고유 VOD 수 (vod_meta_embedding 존재하는 시청 이력만)

    vector_magnitude    DOUBLE PRECISION,

    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    CONSTRAINT fk_user_emb_user
        FOREIGN KEY (user_id_fk) REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT chk_user_emb_vod_count
        CHECK (vod_count >= 0)
);

-- IVFFlat 인덱스: 데이터 적재 완료 후 생성해야 품질이 좋음
-- lists = 500: sqrt(242,702 사용자) ≈ 493 → 500
-- 현재는 초기값 100으로 생성 (적재 후 REINDEX 권장)
CREATE INDEX IF NOT EXISTS idx_user_emb_ivfflat
    ON user_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_user_emb_updated
    ON user_embedding (updated_at DESC);

CREATE TRIGGER trg_user_emb_updated_at
    BEFORE UPDATE ON user_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMIT;

-- 적용 확인
SELECT tablename,
       pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS size
FROM pg_tables
WHERE tablename IN ('vod_meta_embedding', 'user_embedding')
  AND schemaname = 'public'
ORDER BY tablename;
