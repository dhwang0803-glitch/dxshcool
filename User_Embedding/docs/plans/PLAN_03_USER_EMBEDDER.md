# PLAN_03: 유저 임베딩 생성

**목표**: 유저별 시청 VOD 결합 벡터를 completion_rate로 가중 평균 → L2 정규화 → 896차원 유저 벡터 생성

---

## 입출력

| 항목 | 내용 |
|------|------|
| **입력** | `history`: `{user_id: [(asset_id, completion_rate), ...]}` (PLAN_01) |
| **입력** | `vod_vectors`: `{asset_id: np.ndarray(896,)}` (PLAN_02) |
| **출력** | `{user_id: np.ndarray(896,)}` — 임베딩 생성에 성공한 유저만 포함 |

---

## 가중 평균 로직

```python
import numpy as np

def build_user_vector(
    items: list[tuple[str, float]],
    vod_vectors: dict[str, np.ndarray]
) -> np.ndarray | None:
    """
    Args:
        items: [(asset_id, completion_rate), ...]
        vod_vectors: {asset_id: ndarray(896,)}
    Returns:
        L2 정규화된 유저 벡터 (896,) 또는 None (유효 시청 없음)
    """
    vecs, weights = [], []
    for asset_id, rate in items:
        if asset_id in vod_vectors:
            vecs.append(vod_vectors[asset_id])
            weights.append(rate)

    if not vecs:
        return None   # 결합 임베딩 있는 VOD 시청 이력 없음

    vecs = np.array(vecs)       # (K, 896)
    weights = np.array(weights) # (K,)
    weights /= weights.sum()    # 정규화

    user_vec = (vecs * weights[:, None]).sum(axis=0)  # (896,)

    # L2 정규화
    norm = np.linalg.norm(user_vec)
    return user_vec / norm if norm > 0 else user_vec
```

---

## 구현 파일: `src/user_embedder.py`

```python
def build_user_embeddings(
    history: dict[str, list[tuple[str, float]]],
    vod_vectors: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """
    Returns:
        {user_id: np.ndarray(896,)}  — 임베딩 생성 성공한 유저만 포함
    """
```

---

## 스킵 조건

| 조건 | 처리 |
|------|------|
| 시청 VOD 중 결합 임베딩 있는 것이 0건 | 해당 유저 건너뜀 + 로그 |
| 가중치 합계 = 0 (completion_rate 전부 0) | 해당 유저 건너뜀 (data_loader에서 사전 필터링됨) |

---

## 검증

```python
user_vectors = build_user_embeddings(history, vod_vectors)

# 샘플 유저 벡터 확인
sample = next(iter(user_vectors.values()))
assert sample.shape == (896,)
assert abs(np.linalg.norm(sample) - 1.0) < 1e-5  # L2 정규화 확인

# 생성률 확인
total = len(history)
generated = len(user_vectors)
print(f"유저 임베딩 생성: {generated:,} / {total:,} ({generated/total*100:.1f}%)")
```

---

**다음**: PLAN_04_DB_EXPORT.md
