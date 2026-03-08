# Phase 4: 확장 테이블 설계 계획

**단계**: Phase 4 / 5
**목표**: 추천 시스템 확장을 위한 임베딩 및 추천 결과 테이블 설계
**산출물**: `schema/create_embedding_tables.sql`
**선행 조건**: Phase 1~3 완료 후 진행

> **아키텍처 결정 (2026-03-08 팀 협의 완료)**
> 벡터 저장소를 **pgvector 단일화**로 결정. 외부 벡터 DB(Milvus) 미사용.
> 실제 벡터(`VECTOR(512)`)와 메타데이터를 PostgreSQL `vod_embedding` 테이블에 함께 저장.
> VOD_Embedding 브랜치의 파이프라인이 이 테이블에 직접 적재.

---

## 1. 확장 테이블 목록

| 테이블명 | 목적 | 의존 테이블 |
|---------|------|-----------|
| vod_embedding | VOD 벡터 임베딩 (벡터 + 메타데이터) | vod |
| vod_recommendation | 추천 결과 캐시 (TTL 7일) | user, vod |

> **참고**: `user_embedding`은 사용자 행동 기반 벡터로 추후 Phase 5 이후 설계 예정.

---

## 2. vod_embedding 테이블

### 목적
VOD 벡터 임베딩 저장 (pgvector `VECTOR(512)`) 및 메타데이터 관리.
VOD_Embedding 브랜치의 `ingest_to_db.py`가 이 테이블에 직접 적재.

### DDL
`schema/create_embedding_tables.sql` 참조 (실제 실행 파일).

### 주요 컬럼

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `embedding` | `VECTOR(512)` | CLIP ViT-B/32 벡터, 10프레임 평균 |
| `embedding_type` | VARCHAR(32) | `VISUAL` / `CONTENT` / `HYBRID` |
| `model_version` | VARCHAR(64) | `clip-ViT-B-32` |
| `source_type` | VARCHAR(32) | `TRAILER` / `FULL` |
| `frame_count` | SMALLINT | 임베딩에 사용된 프레임 수 |
| `vector_magnitude` | REAL | L2 norm (품질 지표) |

### 벡터 검색 인덱스
```sql
-- IVF_FLAT, lists=100 (sqrt(10,000) 기준), 코사인 유사도
CREATE INDEX idx_vod_emb_ivfflat
    ON vod_embedding USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
-- 검색 시: SET ivfflat.probes = 10;
```

---

## 3. vod_recommendation 테이블

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

## 4. 확장 테이블 작업 시 주의사항

1. **Phase 1 완료 후 진행**: vod, user 테이블이 먼저 생성되어야 FK 설정 가능
2. **pgvector 확장 설치 필요**: VPC PostgreSQL에서 `CREATE EXTENSION IF NOT EXISTS vector` 선행 실행
3. **IVFFlat 인덱스 생성 시점**: 데이터 INSERT 완료 후 생성해야 인덱스 품질이 보장됨
4. **vod_recommendation 캐시 전략**: Redis L1 캐시(1시간) + PostgreSQL L2 캐시(7일) 이중 캐싱 설계
5. **두 브랜치 스키마 동기화**: VOD_Embedding의 `ingest_to_db.py`가 이 DDL 기준으로 정렬됨

---

**이전 단계**: PLAN_03_PERFORMANCE_TEST.md
**다음 단계**: PLAN_05_RAG_DB_INTEGRATION.md
