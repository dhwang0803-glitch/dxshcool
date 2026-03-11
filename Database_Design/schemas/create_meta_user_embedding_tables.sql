-- =============================================================
-- Phase 5: VOD 메타데이터 임베딩 + User 임베딩 테이블 DDL
-- 파일: Database_Design/schemas/create_meta_user_embedding_tables.sql
-- 작성일: 2026-03-11
-- =============================================================
-- 배경:
--   VOD_Embedding 브랜치에서 두 종류의 임베딩을 생성한다.
--     1. 영상 임베딩  : CLIP ViT-B/32               → 512차원 (기존 vod_embedding 테이블)
--     2. 메타 임베딩  : paraphrase-multilingual-MiniLM-L12-v2 → 384차원 (신규)
--
--   두 임베딩을 concat하면 896차원 VOD 결합 벡터가 된다.
--   User_Embedding 브랜치에서 이 896차원 잠재 공간에서 사용자 벡터를 학습한다.
--
--   ※ pgvector는 컬럼당 차원이 고정이므로 vod_embedding(512)과 별도 테이블 필요.
--   ※ 차원 축소(PCA/Autoencoder) 여부는 학습 실험 후 결정. 원본은 본 테이블에 보존.
--
-- 실행 전제: create_tables.sql, create_embedding_tables.sql 완료 후 실행
-- =============================================================


-- =============================================================
-- [1] vod_meta_embedding 테이블
--     모델  : paraphrase-multilingual-MiniLM-L12-v2
--     차원  : 384
--     입력  : asset_nm + genre + director + cast_lead + smry 결합 텍스트
-- =============================================================

CREATE TABLE vod_meta_embedding (
    vod_meta_emb_id     BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL UNIQUE,

    -- 벡터 (384차원)
    embedding           VECTOR(384)     NOT NULL,

    -- 임베딩 생성 입력 정보
    input_text          TEXT,
    -- 실제 임베딩에 사용된 결합 텍스트 (디버깅·재현용, 선택 저장)
    source_fields       TEXT[]          NOT NULL
                            DEFAULT ARRAY['asset_nm','genre','director','cast_lead','smry'],
    -- 사용된 메타데이터 컬럼 목록

    -- 모델 정보
    model_name          VARCHAR(100)    NOT NULL
                            DEFAULT 'paraphrase-multilingual-MiniLM-L12-v2',
    embedding_dim       SMALLINT        NOT NULL DEFAULT 384,

    -- 품질 지표
    vector_magnitude    DOUBLE PRECISION,       -- L2 norm (1.0이면 정규화 완료)

    -- 시간
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 제약
    CONSTRAINT fk_vod_meta_emb_vod
        FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT chk_meta_emb_dim
        CHECK (embedding_dim > 0)
);

-- 벡터 유사도 검색 인덱스 (IVFFlat, 코사인 유사도)
-- lists = 400 : sqrt(165,000) ≈ 406 → 전체 VOD 대상 최적값
-- 검색 시: SET ivfflat.probes = 20;
CREATE INDEX idx_vod_meta_emb_ivfflat
    ON vod_meta_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 400);

CREATE INDEX idx_vod_meta_emb_updated ON vod_meta_embedding (updated_at DESC);

CREATE TRIGGER trg_vod_meta_emb_updated_at
    BEFORE UPDATE ON vod_meta_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE vod_meta_embedding IS
    'VOD 메타데이터 임베딩 테이블. paraphrase-multilingual-MiniLM-L12-v2, 384차원. '
    'vod_embedding(512)과 concat하여 896차원 VOD 결합 벡터로 활용.';
COMMENT ON COLUMN vod_meta_embedding.input_text IS
    '임베딩 생성에 사용된 결합 텍스트. asset_nm + genre + director + cast_lead + smry.';
COMMENT ON COLUMN vod_meta_embedding.source_fields IS
    '임베딩 입력에 포함된 vod 컬럼 목록. NULL 컬럼은 자동 제외.';


-- =============================================================
-- [2] user_embedding 테이블
--     차원  : 896 (VOD 영상 512 + VOD 메타 384 concat과 동일 공간)
--     학습  : ALS 행렬 분해 (item latent factor 초기값 = VOD 결합 벡터)
--     브랜치: User_Embedding
-- =============================================================

CREATE TABLE user_embedding (
    user_emb_id         BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL UNIQUE,

    -- 벡터 (896차원 = VOD 영상 512 + VOD 메타 384)
    embedding           VECTOR(896)     NOT NULL,

    -- 모델 정보
    model_name          VARCHAR(100)    NOT NULL DEFAULT 'ALS',
    embedding_dim       SMALLINT        NOT NULL DEFAULT 896,
    factors             SMALLINT        NOT NULL DEFAULT 896,
    -- ALS 학습 시 사용한 factors 수 (embedding_dim과 일치)
    iterations          SMALLINT        NOT NULL DEFAULT 20,
    train_loss          REAL,           -- 학습 최종 loss (선택)

    -- 품질 지표
    vector_magnitude    DOUBLE PRECISION,

    -- 시간
    trained_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    -- 모델 학습(재학습) 시각
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 제약
    CONSTRAINT fk_user_emb_user
        FOREIGN KEY (user_id_fk) REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT chk_user_emb_dim
        CHECK (embedding_dim > 0),
    CONSTRAINT chk_user_emb_factors
        CHECK (factors > 0)
);

-- 벡터 유사도 검색 인덱스 (IVFFlat, 코사인 유사도)
-- lists = 100 : 초기값 (실제 유저 수 확정 후 sqrt(user_count)으로 조정)
-- 검색 시: SET ivfflat.probes = 10;
CREATE INDEX idx_user_emb_ivfflat
    ON user_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX idx_user_emb_trained  ON user_embedding (trained_at DESC);
CREATE INDEX idx_user_emb_updated  ON user_embedding (updated_at DESC);

CREATE TRIGGER trg_user_emb_updated_at
    BEFORE UPDATE ON user_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE user_embedding IS
    'User 임베딩 테이블. ALS 행렬 분해, 896차원. '
    'VOD 결합 벡터(vod_embedding 512 + vod_meta_embedding 384)와 동일 잠재 공간. '
    '차원 축소(PCA/Autoencoder) 적용 시 embedding_dim 및 VECTOR 차원 변경 필요.';
COMMENT ON COLUMN user_embedding.trained_at IS
    '모델 재학습 시각. 배치 학습 주기마다 갱신.';
COMMENT ON COLUMN user_embedding.factors IS
    'ALS 학습 factors 수. 현재 VOD 결합 벡터 차원(896)과 일치시켜 사용.';


-- =============================================================
-- 생성 확인
-- =============================================================
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size
FROM pg_tables
WHERE tablename IN ('vod_meta_embedding', 'user_embedding')
  AND schemaname = 'public'
ORDER BY tablename;

SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('vod_meta_embedding', 'user_embedding')
ORDER BY tablename, indexname;
