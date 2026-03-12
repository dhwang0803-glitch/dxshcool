"""
PLAN_03: 유저 임베딩 생성

유저별 시청 VOD 결합 벡터를 completion_rate로 가중 평균 후 L2 정규화.
결합 임베딩이 존재하는 시청 VOD가 1건 이상인 유저만 생성.
"""
import logging

import numpy as np

logger = logging.getLogger(__name__)


def _build_user_vector(
    items: list[tuple[str, float]],
    vod_vectors: dict[str, np.ndarray],
) -> tuple[np.ndarray | None, int]:
    """
    단일 유저 벡터 계산.

    Returns:
        (L2 정규화된 896차원 벡터, 사용된 고유 VOD 수)
        유효 시청 VOD가 없으면 (None, 0) 반환.
    """
    vecs, weights = [], []
    for asset_id, rate in items:
        if asset_id in vod_vectors:
            vecs.append(vod_vectors[asset_id])
            weights.append(rate)

    if not vecs:
        return None, 0

    mat = np.array(vecs, dtype=np.float32)        # (K, 896)
    w = np.array(weights, dtype=np.float32)       # (K,)
    w /= w.sum()

    user_vec = (mat * w[:, None]).sum(axis=0)     # (896,)
    norm = np.linalg.norm(user_vec)
    if norm > 1e-9:
        user_vec /= norm
    return user_vec, len(vecs)


def build_user_embeddings(
    history: dict[str, list[tuple[str, float]]],
    vod_vectors: dict[str, np.ndarray],
) -> tuple[dict[str, np.ndarray], dict[str, int]]:
    """
    전체 유저 임베딩 생성.

    Args:
        history:     {user_id_fk: [(vod_id_fk, completion_rate), ...]}
        vod_vectors: {vod_id_fk: np.ndarray(896,)}
    Returns:
        user_vectors: {user_id_fk: np.ndarray(896,)}
        vod_counts:   {user_id_fk: int}  — 임베딩 생성에 사용된 VOD 수
    """
    user_vectors: dict[str, np.ndarray] = {}
    vod_counts: dict[str, int] = {}
    skipped = 0

    for uid, items in history.items():
        vec, count = _build_user_vector(items, vod_vectors)
        if vec is None:
            skipped += 1
            continue
        user_vectors[uid] = vec
        vod_counts[uid] = count

    total = len(history)
    generated = len(user_vectors)
    logger.info(
        f"유저 임베딩 생성: {generated:,} / {total:,} ({generated / total * 100:.1f}%)"
        f" | 스킵: {skipped:,}명 (결합 임베딩 있는 시청 VOD 없음)"
    )
    return user_vectors, vod_counts
