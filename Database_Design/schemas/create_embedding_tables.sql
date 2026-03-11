-- =============================================================
-- Phase 4: 임베딩 및 추천 확장 테이블 DDL (pgvector 기반)
-- 파일: Database_Design/schema/create_embedding_tables.sql
-- 작성일: 2026-03-08  /  수정일: 2026-03-11 (user_embedding 추가)
-- 참조: PLAN_04_EXTENSION_TABLES.md
-- =============================================================
-- 목적: VOD 추천 시스템 확장을 위한 임베딩 + 추천 결과 테이블
--
-- 아키텍처:
--   VOD 벡터          → PostgreSQL vod_embedding  (pgvector VECTOR(512))
--   사용자 벡터       → PostgreSQL user_embedding (pgvector VECTOR(512))
--   추천 결과 캐시    → PostgreSQL vod_recommendation (TTL 7일)
--   외부 벡터 DB 없음 → 단일 PostgreSQL로 운영
--
-- 인덱스 설계:
--   vod_embedding  IVF_FLAT lists=100  → sqrt(10,000 VOD)
--   user_embedding IVF_FLAT lists=500  → sqrt(242,702 user) ≈ 493 → 500
--   probes=10  → 검색 정확도 ~95%
--
-- 실행 전제: create_tables.sql, create_indexes.sql 완료 후 실행
-- 실행 순서: pgvector 확장 → vod_embedding → user_embedding → vod_recommendation
-- =============================================================


-- =============================================================
-- [0] pgvector 확장 설치 (VPC PostgreSQL에서 한 번만)
-- =============================================================
CREATE EXTENSION IF NOT EXISTS vector;


-- =============================================================
-- updated_at 트리거 함수 (create_tables.sql에서 이미 생성됨)
-- CREATE OR REPLACE로 안전하게 덮어씀
-- =============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================
-- [1] vod_embedding 테이블
--     벡터(VECTOR(512))와 메타데이터를 함께 저장
--     모델: CLIP ViT-B/32, 512차원, float32
-- =============================================================

CREATE TABLE vod_embedding (
    vod_embedding_id    BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL UNIQUE,

    -- 벡터 데이터 (pgvector)
    embedding           VECTOR(512)     NOT NULL,

    -- 임베딩 정보
    model_name          VARCHAR(100)    NOT NULL DEFAULT 'clip-ViT-B-32',   -- 모델 식별명 (표시용)
    embedding_type      VARCHAR(32)     NOT NULL DEFAULT 'VISUAL',
    -- VISUAL  : 영상 프레임 기반 시각 벡터 (CLIP ViT-B/32, 512차원) ← 현재 사용
    -- CONTENT : 텍스트(줄거리/제목) 기반 의미 벡터
    -- HYBRID  : VISUAL + CONTENT 결합 벡터
    embedding_dim       INTEGER         NOT NULL DEFAULT 512,
    model_version       VARCHAR(64)     NOT NULL DEFAULT 'clip-ViT-B-32',

    -- 벡터 품질 지표
    vector_magnitude    DOUBLE PRECISION,       -- L2 norm (1.0이면 정규화 완료)
    frame_count         SMALLINT,       -- 임베딩에 사용된 프레임 수 (기본 10)

    -- 소스 정보
    source_type         VARCHAR(32)     NOT NULL DEFAULT 'TRAILER',
    -- TRAILER: YouTube 트레일러 영상
    -- FULL   : 전체 영상
    source_url          TEXT,           -- 원본 YouTube URL (선택)

    -- 시간
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 제약
    CONSTRAINT fk_vod_embedding_vod
        FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT chk_embedding_type
        CHECK (embedding_type IN ('VISUAL', 'CONTENT', 'HYBRID')),
    CONSTRAINT chk_source_type
        CHECK (source_type IN ('TRAILER', 'FULL')),
    CONSTRAINT chk_embedding_dim
        CHECK (embedding_dim > 0),
    CONSTRAINT chk_frame_count
        CHECK (frame_count IS NULL OR frame_count > 0)
);

-- =============================================================
-- 벡터 유사도 검색 인덱스 (IVF_FLAT, 코사인 유사도)
-- lists = 100 : sqrt(10,000) — 최대 10K VOD 기준 최적값
-- 검색 시: SET ivfflat.probes = 10; (10% 탐색, 정확도~95%)
-- 주의: 데이터 INSERT 완료 후 생성해야 인덱스 품질이 좋음
-- =============================================================
CREATE INDEX idx_vod_emb_ivfflat
    ON vod_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- 보조 인덱스
CREATE INDEX idx_vod_emb_type    ON vod_embedding (embedding_type);
CREATE INDEX idx_vod_emb_updated ON vod_embedding (updated_at DESC);

-- 트리거
CREATE TRIGGER trg_vod_embedding_updated_at
    BEFORE UPDATE ON vod_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 코멘트
COMMENT ON TABLE vod_embedding IS
    'VOD 벡터 임베딩 테이블. pgvector VECTOR(512). CLIP ViT-B/32 모델, 트레일러 영상 기반.';
COMMENT ON COLUMN vod_embedding.embedding IS
    'CLIP ViT-B/32 영상 임베딩 벡터. 10프레임 균등 추출 후 평균. 코사인 유사도 검색용.';
COMMENT ON COLUMN vod_embedding.vector_magnitude IS
    'L2 norm. 1.0이면 정규화 완료 상태.';
COMMENT ON COLUMN vod_embedding.frame_count IS
    '임베딩 생성에 사용된 프레임 수. 기본 10프레임 균등 추출.';


-- =============================================================
-- [2] 유사도 검색 쿼리 예시
-- =============================================================

-- [예시 A] 특정 VOD와 유사한 VOD 상위 10개 (코사인 유사도)
-- SET ivfflat.probes = 10;  -- 검색 정확도 조정 (기본 1, 높을수록 정확하고 느림)
-- SELECT
--     ve.vod_id_fk,
--     v.asset_nm,
--     v.genre,
--     1 - (ve.embedding <=> target.embedding) AS cosine_similarity
-- FROM vod_embedding ve
-- JOIN vod v ON ve.vod_id_fk = v.full_asset_id
-- CROSS JOIN (
--     SELECT embedding FROM vod_embedding WHERE vod_id_fk = 'yt|a3f7c2d8e1b4...'
-- ) target
-- WHERE ve.vod_id_fk != 'yt|a3f7c2d8e1b4...'
-- ORDER BY ve.embedding <=> target.embedding
-- LIMIT 10;

-- [예시 B] 장르 필터 + 유사도 검색 (pgvector의 핵심 장점: SQL JOIN 가능)
-- SELECT
--     ve.vod_id_fk,
--     v.asset_nm,
--     1 - (ve.embedding <=> $1::vector) AS similarity
-- FROM vod_embedding ve
-- JOIN vod v ON ve.vod_id_fk = v.full_asset_id
-- WHERE v.genre = '로맨스'
-- ORDER BY ve.embedding <=> $1::vector
-- LIMIT 5;


-- =============================================================
-- [3] user_embedding 테이블
--     사용자별 행동 기반 벡터 (watch_history × vod_embedding 가중평균)
--     User_Embedding 브랜치의 build_user_vectors.py가 적재
--     CF_Engine 학습 시 vod_embedding과 함께 입력으로 사용
-- =============================================================

CREATE TABLE user_embedding (
    user_embedding_id   BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL UNIQUE,

    -- 벡터 데이터 (pgvector)
    embedding           VECTOR(512)     NOT NULL,

    -- 임베딩 메타데이터
    model_version       VARCHAR(64)     NOT NULL DEFAULT 'clip-ViT-B-32',
    -- vod_embedding과 동일 모델 기반 가중평균 → 동일 벡터 공간

    -- 입력 데이터 품질
    vod_count           INTEGER         NOT NULL DEFAULT 0,
    -- 임베딩 생성에 사용된 고유 VOD 수 (watch_history 중 clip_embeddings 존재하는 것)

    vector_magnitude    DOUBLE PRECISION,
    -- L2 norm (1.0이면 정규화 완료)

    -- 시간
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 제약
    CONSTRAINT fk_user_embedding_user
        FOREIGN KEY (user_id_fk) REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT chk_user_emb_vod_count
        CHECK (vod_count >= 0)
);

-- =============================================================
-- 벡터 유사도 검색 인덱스 (IVF_FLAT, 코사인 유사도)
-- lists = 500 : sqrt(242,702 사용자) ≈ 493 → 500 (pgvector 권장 공식)
-- 용도: "나와 비슷한 사용자 찾기" (협업 필터링 보조)
-- 주의: 데이터 INSERT 완료 후 생성해야 인덱스 품질이 좋음
-- =============================================================
CREATE INDEX idx_user_emb_ivfflat
    ON user_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 500);

-- 보조 인덱스
CREATE INDEX idx_user_emb_updated ON user_embedding (updated_at DESC);

-- 트리거
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

-- =============================================================
-- [3-1] 사용자 벡터 생성 쿼리 예시 (User_Embedding 파이프라인 참고용)
-- =============================================================

-- [예시] 특정 사용자의 임베딩 벡터 조회 후 유사 VOD 추천
-- SET ivfflat.probes = 10;
-- SELECT
--     ve.vod_id_fk,
--     v.asset_nm,
--     1 - (ve.embedding <=> ue.embedding) AS cosine_similarity
-- FROM user_embedding ue
-- JOIN vod_embedding ve ON TRUE
-- JOIN vod v ON ve.vod_id_fk = v.full_asset_id
-- WHERE ue.user_id_fk = $1
-- ORDER BY ve.embedding <=> ue.embedding
-- LIMIT 10;


-- =============================================================
-- [4] vod_recommendation 테이블
--     사용자별 추천 결과 캐시 (TTL 7일)
--     추천 엔진(로컬)이 계산 후 결과만 VPC DB에 저장
-- =============================================================

CREATE TABLE vod_recommendation (
    recommendation_id   BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,

    -- 추천 순위 및 점수
    rank                SMALLINT        NOT NULL,   -- 해당 사용자에게 몇 번째 추천인지
    score               REAL            NOT NULL,   -- 코사인 유사도 (0~1)

    -- 추천 방식
    recommendation_type VARCHAR(32)     NOT NULL DEFAULT 'VISUAL_SIMILARITY',
    -- VISUAL_SIMILARITY : CLIP 임베딩 코사인 유사도 기반
    -- COLLABORATIVE     : 협업 필터링 (행렬분해)
    -- HYBRID            : 복합

    -- TTL 관리
    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '7 days',

    -- 제약
    CONSTRAINT fk_vod_rec_user
        FOREIGN KEY (user_id_fk) REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_vod_rec_vod
        FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    CONSTRAINT uq_vod_rec_user_vod
        UNIQUE (user_id_fk, vod_id_fk),
    CONSTRAINT chk_rec_score
        CHECK (score >= 0 AND score <= 1),
    CONSTRAINT chk_rec_rank
        CHECK (rank >= 1),
    CONSTRAINT chk_rec_type
        CHECK (recommendation_type IN ('VISUAL_SIMILARITY', 'COLLABORATIVE', 'HYBRID'))
);

-- 인덱스
CREATE INDEX idx_vod_rec_user    ON vod_recommendation (user_id_fk, rank);
CREATE INDEX idx_vod_rec_expires ON vod_recommendation (expires_at);  -- TTL 만료 삭제용

-- 코멘트
COMMENT ON TABLE vod_recommendation IS
    '사용자별 추천 결과 캐시. 추천 엔진이 로컬에서 계산 후 결과만 저장. TTL 7일.';
COMMENT ON COLUMN vod_recommendation.expires_at IS
    'TTL 만료 시각. db_maintenance.py 자정 실행 시 만료된 레코드 삭제.';


-- =============================================================
-- [5] TTL 만료 추천 삭제 — db_maintenance.py에서 자정 실행
-- =============================================================
-- DELETE FROM vod_recommendation WHERE expires_at < NOW();


-- =============================================================
-- 생성 확인
-- =============================================================
-- pgvector 설치 확인
SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';

-- 테이블 및 크기 확인
SELECT
    tablename,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size
FROM pg_tables
WHERE tablename IN ('vod_embedding', 'user_embedding', 'vod_recommendation')
  AND schemaname = 'public'
ORDER BY tablename;

-- 인덱스 확인
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename IN ('vod_embedding', 'user_embedding')
ORDER BY tablename, indexname;
