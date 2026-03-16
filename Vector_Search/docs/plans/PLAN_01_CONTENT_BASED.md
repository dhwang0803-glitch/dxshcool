# PLAN_01: 메타데이터 기반 콘텐츠 유사도

**파일**: `src/content_based.py`
**입력**: `public.vod_meta_embedding` 테이블 (384차원, VOD_Embedding 브랜치 적재)
**출력**: pgvector 코사인 유사도 스코어

---

## 목표

`VOD_Embedding` 브랜치가 적재한 `vod_meta_embedding` 테이블의 384차원 벡터를 pgvector로 검색한다.
로컬 인덱스 빌드 없이 DB에서 직접 검색한다.

---

## 모델 (참고)

- **SBERT**: `paraphrase-multilingual-MiniLM-L12-v2`
- 차원: **384차원** float32
- 입력: `asset_nm + genre + director + cast_lead + smry` 결합 텍스트
- ※ 임베딩 생성은 VOD_Embedding 브랜치 담당. Vector_Search는 읽기만 한다.

---

## 사전 조건

- `vod_meta_embedding` 테이블 존재 및 데이터 적재 완료 (VOD_Embedding 브랜치 작업)
- IVFFlat 인덱스 생성 완료 (lists=400, Database_Design 스키마 기준):
  ```sql
  CREATE INDEX idx_vod_meta_emb_ivfflat ON vod_meta_embedding
      USING ivfflat (embedding vector_cosine_ops) WITH (lists = 400);
  ```

---

## 구현 (`src/content_based.py`)

```python
import psycopg2
from pgvector.psycopg2 import register_vector

def get_similar_by_meta(vod_id: str, conn, top_n: int = 20) -> list[dict]:
    """
    메타데이터 벡터 기반 유사 VOD TOP-N 반환.
    반환: [{"vod_id": str, "content_score": float}, ...]
    """
    register_vector(conn)
    cur = conn.cursor()

    cur.execute(
        "SELECT embedding FROM vod_meta_embedding WHERE vod_id_fk = %s",
        (vod_id,)
    )
    row = cur.fetchone()
    if row is None:
        return []

    query_vec = row[0]

    # probes는 config/search_config.yaml에서 단일 관리
    cur.execute("SET ivfflat.probes = %(probes)s", {"probes": 20})
    cur.execute(
        """
        SELECT vod_id_fk,
               1 - (embedding <=> %s::vector) AS content_score
        FROM vod_meta_embedding
        WHERE vod_id_fk != %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """,
        (query_vec, vod_id, query_vec, top_n)
    )
    return [{"vod_id": r[0], "content_score": float(r[1])} for r in cur.fetchall()]
```

---

## 검색 흐름

```
쿼리 vod_id → vod_meta_embedding에서 벡터 조회 → pgvector <=> 코사인 검색 → TOP-N 반환
```

---

## 주의사항

- `vod_meta_embedding` 커버리지: VOD_Embedding 브랜치 실행 결과에 따라 다름
- `ivfflat.probes = 20` → `config/search_config.yaml`에서 단일 관리
- 로컬 `content_index.pkl` 빌드 불필요 — DB 인덱스 사용
- `scripts/build_index.py` 불필요

---

**다음**: PLAN_02_CLIP_BASED.md
