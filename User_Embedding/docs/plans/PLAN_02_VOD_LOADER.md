# PLAN_02: VOD 결합 임베딩 로더

**목표**: DB `vod_embedding`(CLIP 512) + `vod_meta_embedding`(METADATA 384) 두 테이블에서 임베딩을 읽어 L2 정규화 후 concat → 896차원 VOD 결합 벡터 딕셔너리 반환

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력 (CLIP)** | DB `vod_embedding` 테이블 — CLIP ViT-B/32, 512차원 |
| **입력 (METADATA)** | DB `vod_meta_embedding` 테이블 — paraphrase-multilingual-MiniLM-L12-v2, 384차원 |
| **출력** | `{asset_id: np.ndarray(896,)}` — 두 테이블 모두 존재하는 asset만 포함 |

> ⚠️ METADATA 임베딩은 `vod_embedding`이 아닌 **`vod_meta_embedding`** 테이블에 저장된다.
> (`VOD_Embedding` 브랜치 설계: 차원이 다른 벡터는 별도 테이블로 분리)

---

## DB 쿼리

```sql
-- CLIP 임베딩 (512차원) — vod_embedding 테이블
SELECT vod_id_fk, embedding
FROM vod_embedding
ORDER BY vod_id_fk;

-- METADATA 임베딩 (384차원) — vod_meta_embedding 테이블 (별도 테이블 주의)
SELECT vod_id_fk, embedding
FROM vod_meta_embedding
ORDER BY vod_id_fk;
```

> 두 테이블 모두에 `vod_id_fk`가 존재하는 asset만 결합. 한쪽만 있는 경우 제외하고 로그 출력.

---

## 결합 로직

```python
import numpy as np

def l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v   # zero-vector 방어

# asset_id 기준 inner join 후
combined = np.concatenate([
    l2_normalize(clip_vec),   # 512차원
    l2_normalize(meta_vec),   # 384차원
])  # → 896차원
```

---

## 구현 파일: `src/vod_embedding_loader.py`

```python
def load_vod_combined(conn, asset_ids: list[str] | None = None) -> dict[str, np.ndarray]:
    """
    Args:
        asset_ids: None이면 전체 로드. 지정 시 해당 asset만 조회 (필요한 것만 로드해 메모리 절약).
    Returns:
        {asset_id: np.ndarray(896,) float32}
    """
```

> `asset_ids`를 PLAN_01 결과에서 추출해 전달하면 불필요한 VOD 임베딩 로드를 줄일 수 있다.

---

## 예외 처리

| 상황 | 처리 |
|------|------|
| CLIP만 있고 METADATA 없는 VOD | 제외 + `logger.warning` |
| METADATA만 있고 CLIP 없는 VOD | 제외 + `logger.warning` |
| zero-vector | L2 norm = 0이면 정규화 skip (원본 유지) |
| 요청된 asset_ids 중 결합 임베딩 없는 항목 | 반환 dict에서 누락 (호출부에서 처리) |

---

## 검증

```python
vod_vectors = load_vod_combined(conn)

# 차원 확인
sample = next(iter(vod_vectors.values()))
assert sample.shape == (896,)

# CLIP 파트 L2 norm ≈ 1.0
clip_part = sample[:512]
assert abs(np.linalg.norm(clip_part) - 1.0) < 1e-5

# METADATA 파트 L2 norm ≈ 1.0
meta_part = sample[512:]
assert abs(np.linalg.norm(meta_part) - 1.0) < 1e-5

print(f"VOD 결합 임베딩 로드 완료: {len(vod_vectors):,}건")
```

---

**다음**: PLAN_03_USER_EMBEDDER.md
