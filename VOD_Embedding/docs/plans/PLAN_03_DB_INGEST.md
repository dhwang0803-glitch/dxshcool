# PLAN_03: pgvector DB 적재

**브랜치**: VOD_Embedding
**스크립트**: `pipeline/ingest_to_db.py`
**입력**: `data/video_embs_batch_*.pkl`
**출력**: `vod_embedding` 테이블 (PostgreSQL + pgvector)

---

## 목표

PLAN_02에서 생성한 배치 pkl 파일들을 VPC PostgreSQL의 `vod_embedding` 테이블에 적재:
1. `CREATE EXTENSION IF NOT EXISTS vector` 확인
2. `vod_embedding` 테이블 존재 확인 (없으면 DDL 참조)
3. pkl 배치 파일 순서대로 INSERT (ON CONFLICT DO UPDATE)
4. 적재 완료 건수 검증

---

## 사전 준비

### 1. pgvector 확장 확인

```sql
-- VPC에서 직접 실행
CREATE EXTENSION IF NOT EXISTS vector;
SELECT extversion FROM pg_extension WHERE extname = 'vector';
```

### 2. 테이블 생성

`Database_Design/schema/create_embedding_tables.sql` 실행:

```sql
CREATE TABLE IF NOT EXISTS vod_embedding (
    vod_embedding_id  BIGSERIAL PRIMARY KEY,
    vod_id_fk         VARCHAR(64) NOT NULL REFERENCES vod(full_asset_id),
    embedding         VECTOR(512) NOT NULL,
    model_name        VARCHAR(100) NOT NULL DEFAULT 'clip-ViT-B-32',
    vector_magnitude  FLOAT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vod_embedding UNIQUE (vod_id_fk, model_name)
);

CREATE INDEX idx_vod_emb_ivfflat ON vod_embedding
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

> IVF_FLAT 인덱스는 데이터 적재 후 생성 권장
> (빈 테이블에 인덱스 후 INSERT하면 인덱스 효율 저하)

---

## INSERT 전략

### pgvector 문자열 포맷

```python
def to_pgvector_str(vec: np.ndarray) -> str:
    """numpy float32 → '[f1,f2,...,f512]' 문자열"""
    return '[' + ','.join(f'{x:.8f}' for x in vec) + ']'
```

### 배치 INSERT (psycopg2)

```python
INSERT_SQL = """
INSERT INTO vod_embedding (vod_id_fk, embedding, model_name, vector_magnitude)
VALUES (%(vod_id)s, %(embedding)s::vector, %(model_name)s, %(magnitude)s)
ON CONFLICT (vod_id_fk, model_name)
DO UPDATE SET
    embedding        = EXCLUDED.embedding,
    vector_magnitude = EXCLUDED.vector_magnitude,
    updated_at       = NOW()
"""
```

- `ON CONFLICT DO UPDATE`: 재실행 시 안전하게 덮어쓰기 (멱등성)
- 배치 INSERT: `executemany()` 대신 루프 + 1,000건마다 `COMMIT` (메모리 관리)

---

## IVF_FLAT 인덱스 생성 타이밍

```sql
-- 전체 적재 완료 후 실행 (데이터 있을 때 더 효율적)
CREATE INDEX idx_vod_emb_ivfflat ON vod_embedding
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

- lists=100: pgvector 권장값 = sqrt(row_count), 최대 10,000 VOD 기준
- 인덱스 생성 소요: 수 분 (10K 행 기준)

---

## 검색 설정 (적재 후 사용 시)

```sql
-- 검색 전 probes 설정 (정확도/속도 균형)
SET ivfflat.probes = 10;  -- 10% of lists, ~95% accuracy

-- 코사인 유사도 기반 TOP-5 검색
SELECT ve.vod_id_fk, v.asset_nm,
       1 - (ve.embedding <=> $1::vector) AS similarity
FROM vod_embedding ve
JOIN vod v ON ve.vod_id_fk = v.full_asset_id
ORDER BY ve.embedding <=> $1::vector
LIMIT 5;
```

---

## 실행 방법

```bash
conda activate myenv

# 전체 pkl 배치 적재
python pipeline/ingest_to_db.py

# 특정 배치 파일만 적재
python pipeline/ingest_to_db.py --batch data/video_embs_batch_001.pkl

# 드라이런 (DB 접속 확인만, INSERT 없음)
python pipeline/ingest_to_db.py --dry-run

# 적재 결과 검증
python pipeline/ingest_to_db.py --verify
```

---

## 검증 쿼리

```sql
-- 적재 건수 확인
SELECT COUNT(*) FROM vod_embedding;

-- 모델별 분포
SELECT model_name, COUNT(*) FROM vod_embedding GROUP BY model_name;

-- vod 테이블 대비 커버리지
SELECT
    (SELECT COUNT(*) FROM vod_embedding) AS embedded,
    (SELECT COUNT(*) FROM vod)           AS total_vod,
    ROUND(
        (SELECT COUNT(*) FROM vod_embedding)::numeric /
        (SELECT COUNT(*) FROM vod) * 100, 1
    ) AS coverage_pct;

-- 이상 벡터 확인
SELECT COUNT(*) FROM vod_embedding WHERE vector_magnitude < 0.01 OR vector_magnitude > 100;
```

목표: vod 45,000개 중 **70% 이상** (31,500개+) 적재

---

## 진행 상황 예측

| 항목 | 수치 |
|------|------|
| 예상 적재 건수 | 28,000~36,000개 |
| INSERT 속도 | ~2,000건/분 |
| 총 소요 시간 | **14~18분** |

---

**이전**: PLAN_02_BATCH_EMBED.md
**완료 후**: VPC vod_embedding 테이블 확인 → 추천 API 연동 시작
