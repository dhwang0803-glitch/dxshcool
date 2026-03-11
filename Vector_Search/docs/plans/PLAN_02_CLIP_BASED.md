# PLAN_02: CLIP 영상 기반 유사도

**파일**: `src/clip_based.py`
**입력**: vod_embedding 테이블 (CLIP 512차원 벡터)
**출력**: pgvector 코사인 유사도 스코어

---

## 목표

`VOD_Embedding` 브랜치가 적재한 `vod_embedding` 테이블의 CLIP 512차원 벡터를 pgvector로 검색한다.

---

## 사전 조건

- `vod_embedding` 테이블 존재 및 데이터 적재 완료 (VOD_Embedding 브랜치 작업)
- pgvector 확장 설치: `CREATE EXTENSION IF NOT EXISTS vector`
- IVFFlat 인덱스 생성 완료:
  ```sql
  CREATE INDEX idx_vod_emb_ivfflat ON vod_embedding
      USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
  ```

---

## 구현 (`src/clip_based.py`)

```python
import psycopg2
from pgvector.psycopg2 import register_vector
import numpy as np

def get_similar_by_clip(vod_id: str, conn, top_n: int = 20) -> list[dict]:
    """
    CLIP 벡터 기반 유사 VOD TOP-N 반환.
    반환: [{"vod_id": str, "clip_score": float}, ...]
    """
    register_vector(conn)
    cur = conn.cursor()

    # 쿼리 벡터 조회
    cur.execute(
        "SELECT embedding FROM vod_embedding WHERE vod_id_fk = %s AND model_name = 'clip-ViT-B-32'",
        (vod_id,)
    )
    row = cur.fetchone()
    if row is None:
        return []

    query_vec = row[0]

    # pgvector 코사인 검색 (probes=10 설정)
    cur.execute("SET ivfflat.probes = 10")
    cur.execute(
        """
        SELECT vod_id_fk,
               1 - (embedding <=> %s::vector) AS clip_score
        FROM vod_embedding
        WHERE vod_id_fk != %s
          AND model_name = 'clip-ViT-B-32'
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_vec, vod_id, query_vec, top_n)
    )
    return [{"vod_id": r[0], "clip_score": float(r[1])} for r in cur.fetchall()]
```

---

## 주의사항

- `vod_embedding` 커버리지: vod 전체의 약 70% 예상 (나머지는 clip_score=0 처리)
- `model_name = 'clip-ViT-B-32'` 필터 필수 (fallback 텍스트 임베딩과 구분)
- `ivfflat.probes = 10` → 정확도 ~95%, 필요 시 조정

---

**다음**: PLAN_03_ENSEMBLE.md
