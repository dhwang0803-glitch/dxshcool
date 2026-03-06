# Phase 4: 확장 테이블 설계 계획

**단계**: Phase 4 / 5
**목표**: 추천 시스템 확장을 위한 임베딩 및 추천 결과 테이블 설계
**산출물**: `schema/create_embedding_tables.sql`, `schema/create_recommendation_table.sql`
**선행 조건**: Phase 1~3 완료 후 진행

---

## 1. 확장 테이블 목록

| 테이블명 | 목적 | 의존 테이블 |
|---------|------|-----------|
| vod_embedding | VOD 벡터 임베딩 메타데이터 | vod |
| user_embedding | 사용자 임베딩 메타데이터 | user |
| vod_recommendation | 추천 결과 캐시 (TTL 7일) | user, vod |

> **주의**: 실제 벡터 데이터는 Milvus에 저장. PostgreSQL에는 메타데이터만 저장.

---

## 2. vod_embedding 테이블

### 목적
Milvus에 저장된 VOD 벡터의 메타데이터 관리 및 버전 추적

### DDL (PostgreSQL)

```sql
CREATE TABLE vod_embedding (
    vod_embedding_id    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64) NOT NULL UNIQUE,

    -- Milvus 참조
    milvus_collection   VARCHAR(128),       -- 예: "vod_content_v1"
    milvus_vector_id    BIGINT,             -- Milvus 내부 PK

    -- 임베딩 정보
    embedding_type      VARCHAR(32) NOT NULL,   -- CONTENT / METADATA / VISUAL / HYBRID
    embedding_dim       INTEGER NOT NULL,        -- 1536, 384, 512, 2432
    model_version       VARCHAR(64),            -- 예: "openai-embedding-3-large"

    -- 벡터 통계 (선택적 최적화)
    vector_magnitude    REAL,               -- L2 norm

    -- 시간 정보
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    -- FK
    CONSTRAINT fk_vod_embedding_vod
        FOREIGN KEY (vod_id_fk) REFERENCES vod (full_asset_id) ON DELETE CASCADE
);

-- 인덱스
CREATE INDEX idx_vod_emb_type ON vod_embedding (embedding_type);
CREATE INDEX idx_vod_emb_updated ON vod_embedding (updated_at);

-- updated_at 트리거
CREATE TRIGGER trg_vod_embedding_updated_at
    BEFORE UPDATE ON vod_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 코멘트
COMMENT ON TABLE vod_embedding IS 'Milvus VOD 벡터 임베딩 메타데이터 (실제 벡터는 Milvus에 저장)';
COMMENT ON COLUMN vod_embedding.embedding_type IS 'CONTENT: 콘텐츠 벡터(1536차원), METADATA: 텍스트 벡터(384차원), VISUAL: 이미지 벡터(512차원), HYBRID: 복합 벡터(2432차원)';
```

---

## 3. user_embedding 테이블

### 목적
사용자 행동 기반 벡터 임베딩의 메타데이터 및 생성 이력 관리

### DDL (PostgreSQL)

```sql
CREATE TABLE user_embedding (
    user_embedding_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64) NOT NULL,

    -- Milvus 참조
    milvus_collection   VARCHAR(128),
    milvus_vector_id    BIGINT,

    -- 임베딩 정보
    embedding_type      VARCHAR(32) NOT NULL,   -- BEHAVIOR / PREFERENCE / DEMOGRAPHIC / HYBRID
    embedding_dim       INTEGER NOT NULL,        -- 256, 128, 64, 448
    model_version       VARCHAR(64),

    -- 생성 기반 정보
    base_record_count   INTEGER,    -- 임베딩 생성에 사용된 watch_history 건수
    base_date_from      DATE,       -- 데이터 기준 시작일
    base_date_to        DATE,       -- 데이터 기준 종료일

    -- 시간 정보
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),

    -- 제약조건
    CONSTRAINT fk_user_embedding_user
        FOREIGN KEY (user_id_fk) REFERENCES "user" (sha2_hash) ON DELETE CASCADE,
    CONSTRAINT uq_user_embedding_type
        UNIQUE (user_id_fk, embedding_type)     -- 사용자당 타입별 1개만
);

-- 인덱스
CREATE INDEX idx_user_emb_type ON user_embedding (embedding_type);
CREATE INDEX idx_user_emb_updated ON user_embedding (updated_at);

-- updated_at 트리거
CREATE TRIGGER trg_user_embedding_updated_at
    BEFORE UPDATE ON user_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE user_embedding IS '사용자 행동 기반 벡터 임베딩 메타데이터 (실제 벡터는 Milvus에 저장)';
COMMENT ON COLUMN user_embedding.embedding_type IS 'BEHAVIOR: 시청 패턴(256차원), PREFERENCE: 장르 선호도(128차원), DEMOGRAPHIC: 인구통계(64차원), HYBRID: 복합(448차원)';
```

---

## 4. vod_recommendation 테이블

### 목적
Milvus 벡터 검색 + Re-Ranking 결과를 캐시 (TTL: 7일)

### DDL (PostgreSQL)

```sql
CREATE TABLE vod_recommendation (
    recommendation_id   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64) NOT NULL,
    vod_id_fk           VARCHAR(64) NOT NULL,

    -- 순위 정보
    rank_initial        INTEGER NOT NULL,   -- Milvus 검색 1차 순위 (1~1000)
    rank_final          INTEGER NOT NULL,   -- Re-Ranking 후 최종 순위

    -- 점수
    similarity_score    REAL NOT NULL,      -- 벡터 유사도 (0.0 ~ 1.0)
    rerank_score        REAL NOT NULL,      -- Re-Ranking 최종 점수

    -- Re-Ranking 상세 정보
    rerank_factors      JSONB,
    -- 예시:
    -- {
    --   "freshness": 0.8,
    --   "popularity": 0.6,
    --   "user_preference_match": 0.9,
    --   "diversity_penalty": -0.1,
    --   "cold_start_boost": 0.2
    -- }

    -- 추천 설명
    reason              VARCHAR(255),       -- "유사 장르 추천", "인기 상승 작품" 등

    -- 캐시 관리
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    expired_at          TIMESTAMPTZ,        -- created_at + INTERVAL '7 days'

    -- 피드백 (재학습용)
    is_clicked          BOOLEAN DEFAULT FALSE,
    is_watched          BOOLEAN DEFAULT FALSE,
    click_at            TIMESTAMPTZ,

    -- FK
    CONSTRAINT fk_rec_user
        FOREIGN KEY (user_id_fk) REFERENCES "user" (sha2_hash) ON DELETE CASCADE,
    CONSTRAINT fk_rec_vod
        FOREIGN KEY (vod_id_fk) REFERENCES vod (full_asset_id) ON DELETE CASCADE,

    -- 복합 유니크: 동일 사용자-VOD 조합은 생성 시각 기준 1건
    CONSTRAINT uq_recommendation
        UNIQUE (user_id_fk, vod_id_fk, created_at)
);

-- 인덱스
CREATE INDEX idx_rec_user_id ON vod_recommendation (user_id_fk);
CREATE INDEX idx_rec_vod_id ON vod_recommendation (vod_id_fk);
CREATE INDEX idx_rec_rank_final ON vod_recommendation (rank_final);
CREATE INDEX idx_rec_rerank_score ON vod_recommendation (rerank_score DESC);
CREATE INDEX idx_rec_expired_at ON vod_recommendation (expired_at);

-- TTL 관리용 부분 인덱스 (만료되지 않은 추천만)
CREATE INDEX idx_rec_active
    ON vod_recommendation (user_id_fk, rank_final)
    WHERE expired_at > NOW() OR expired_at IS NULL;

COMMENT ON TABLE vod_recommendation IS 'VOD 추천 결과 캐시 (TTL 7일). 실제 추천 엔진은 Milvus + Re-Ranking 파이프라인에서 생성';
COMMENT ON COLUMN vod_recommendation.rerank_factors IS 'Re-Ranking 각 요소 점수 (JSONB): freshness, popularity, user_preference_match, diversity_penalty, cold_start_boost';
```

### TTL 관리 쿼리

```sql
-- 만료된 추천 삭제 (일 1회 배치, 클릭하지 않은 항목만)
DELETE FROM vod_recommendation
WHERE expired_at < NOW()
  AND is_clicked = FALSE;

-- expired_at 자동 설정 트리거 (INSERT 시)
CREATE OR REPLACE FUNCTION set_recommendation_expiry()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.expired_at IS NULL THEN
        NEW.expired_at = NEW.created_at + INTERVAL '7 days';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_rec_set_expiry
    BEFORE INSERT ON vod_recommendation
    FOR EACH ROW
    EXECUTE FUNCTION set_recommendation_expiry();
```

---

## 5. 확장 테이블 작업 시 주의사항

1. **Phase 1 완료 후 진행**: vod, user 테이블이 먼저 생성되어야 FK 설정 가능
2. **Milvus 연동 별도**: 실제 벡터 저장/검색은 RAG 팀 또는 별도 서비스에서 담당
3. **vod_recommendation 캐시 전략**: Redis L1 캐시(1시간) + PostgreSQL L2 캐시(7일) 이중 캐싱 설계
4. **JSONB 선택 이유**: PostgreSQL에서 JSON보다 JSONB가 인덱싱 및 조회 성능 우수
5. **부분 인덱스 `idx_rec_active`**: 만료된 레코드는 인덱스에서 제외하여 효율성 향상 (단, `NOW()` 기준이므로 인덱스 갱신 필요)

---

**이전 단계**: PLAN_03_PERFORMANCE_TEST.md
**다음 단계**: PLAN_05_RAG_DB_INTEGRATION.md
