# PLAN_04: user_embedding DB 적재

**목표**: 생성된 유저 벡터를 `user_embedding` 테이블에 upsert

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | `{user_id_fk: np.ndarray(896,)}` (PLAN_03) |
| **출력** | `user_embedding` 테이블 upsert 완료 |

---

## 테이블 스키마 (Database_Design 브랜치 기준)

```sql
-- migrations/20260311_add_meta_user_embedding_tables.sql 참조
CREATE TABLE user_embedding (
    user_emb_id         BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL UNIQUE,  -- "user".sha2_hash FK
    embedding           VECTOR(896)     NOT NULL,
    model_name          VARCHAR(100)    NOT NULL DEFAULT 'weighted_mean',
    vod_count           INTEGER         NOT NULL DEFAULT 0,
    vector_magnitude    DOUBLE PRECISION,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);
```

> ⚠️ PK 컬럼은 `user_emb_id`(자동 생성). 비즈니스 키는 `user_id_fk`(UNIQUE).
> upsert 충돌 기준은 `user_id_fk`를 사용한다.

---

## upsert 쿼리

```sql
INSERT INTO user_embedding (user_id_fk, embedding, vod_count, updated_at)
VALUES (%s, %s, %s, NOW())
ON CONFLICT (user_id_fk)
DO UPDATE SET
    embedding       = EXCLUDED.embedding,
    vod_count       = EXCLUDED.vod_count,
    updated_at      = NOW();
```

---

## 배치 처리

- 1,000건 단위 배치 upsert (메모리 및 트랜잭션 크기 균형)
- `psycopg2.extras.execute_batch` 사용

```python
from pgvector.psycopg2 import register_vector
from psycopg2.extras import execute_batch

register_vector(conn)

BATCH_SIZE = 1000
# user_vectors: {user_id_fk: np.ndarray(896,)}
# vod_counts:   {user_id_fk: int}  — 임베딩 생성에 사용된 고유 VOD 수
rows = [(uid, vec.tolist(), vod_counts.get(uid, 0)) for uid, vec in user_vectors.items()]

for i in range(0, len(rows), BATCH_SIZE):
    batch = rows[i:i + BATCH_SIZE]
    execute_batch(cur,
        "INSERT INTO user_embedding (user_id_fk, embedding, vod_count, updated_at) "
        "VALUES (%s, %s, %s, NOW()) "
        "ON CONFLICT (user_id_fk) DO UPDATE SET "
        "embedding = EXCLUDED.embedding, "
        "vod_count = EXCLUDED.vod_count, "
        "updated_at = NOW()",
        batch
    )
    conn.commit()
```

---

## 구현 파일: `scripts/run_embed.py`

전체 파이프라인 진입점 (PLAN_01 ~ PLAN_04 순서대로 실행):

```
run_embed.py
  └─ data_loader.load_watch_history()
  └─ vod_embedding_loader.load_vod_combined(asset_ids)
  └─ user_embedder.build_user_embeddings()
  └─ DB upsert (배치)
  └─ (--verify 옵션) 적재 건수 검증
```

### 실행 옵션

| 옵션 | 설명 |
|------|------|
| (없음) | 전체 유저 처리 |
| `--pilot N` | N명 유저만 처리 (정상 동작 확인용) |
| `--user-id ID` | 특정 유저 1명 재계산 |
| `--verify` | 적재 건수 / 샘플 벡터 출력만 |

---

## 검증 쿼리

```sql
-- 적재 건수
SELECT COUNT(*) FROM user_embedding;

-- 샘플 확인
SELECT user_id_fk, vod_count, vector_magnitude, updated_at
FROM user_embedding
LIMIT 3;

-- 벡터 차원 확인 (pgvector)
SELECT user_id_fk, vector_dims(embedding) AS dim
FROM user_embedding
LIMIT 1;
-- 기대값: dim = 896
```

---

**완료**: 전체 파이프라인 구현 체크리스트는 PLAN_00_MASTER.md 참고
