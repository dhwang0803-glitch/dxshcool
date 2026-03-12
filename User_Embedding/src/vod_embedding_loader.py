"""
PLAN_02: VOD 결합 임베딩 로더

vod_embedding (CLIP 512차원) + vod_meta_embedding (METADATA 384차원)을
inner join하여 L2 정규화 후 concat → 896차원 결합 벡터로 반환한다.
두 테이블 모두에 vod_id_fk가 존재하는 VOD만 결합 대상.
"""
import logging

import numpy as np
import psycopg2.extras

logger = logging.getLogger(__name__)

CLIP_DIM = 512
META_DIM = 384
COMBINED_DIM = CLIP_DIM + META_DIM  # 896


def _l2_normalize(v: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-9 else v


def load_vod_combined(
    conn,
    asset_ids: list[str] | None = None,
) -> dict[str, np.ndarray]:
    """
    VOD 결합 임베딩 (CLIP 512 + META 384 = 896차원) 로드.

    Args:
        asset_ids: None이면 전체 로드. 지정 시 해당 vod_id_fk만 조회.
    Returns:
        {vod_id_fk: np.ndarray(896,) float32}
        두 테이블 모두 존재하는 VOD만 포함.
    """
    logger.info("VOD 임베딩 로드 중...")

    # --- CLIP 임베딩 로드 ---
    def _parse_vec(raw) -> np.ndarray:
        """pgvector 컬럼을 문자열로 받아 numpy array로 변환."""
        return np.fromstring(str(raw).strip("[]"), sep=",", dtype=np.float32)

    clip_vecs: dict[str, np.ndarray] = {}
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        if asset_ids:
            cur.execute(
                "SELECT vod_id_fk, embedding::text FROM vod_embedding WHERE vod_id_fk = ANY(%s)",
                (asset_ids,),
            )
        else:
            cur.execute("SELECT vod_id_fk, embedding::text FROM vod_embedding ORDER BY vod_id_fk")
        for row in cur:
            clip_vecs[row["vod_id_fk"]] = _parse_vec(row["embedding"])
    logger.info(f"  CLIP 임베딩: {len(clip_vecs):,}건")

    # --- METADATA 임베딩 로드 ---
    meta_vecs: dict[str, np.ndarray] = {}
    with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
        if asset_ids:
            cur.execute(
                "SELECT vod_id_fk, embedding::text FROM vod_meta_embedding WHERE vod_id_fk = ANY(%s)",
                (asset_ids,),
            )
        else:
            cur.execute("SELECT vod_id_fk, embedding::text FROM vod_meta_embedding ORDER BY vod_id_fk")
        for row in cur:
            meta_vecs[row["vod_id_fk"]] = _parse_vec(row["embedding"])
    logger.info(f"  META 임베딩: {len(meta_vecs):,}건")

    # --- inner join: 두 테이블 모두 있는 VOD만 결합 ---
    clip_only = len(clip_vecs) - len(set(clip_vecs) & set(meta_vecs))
    meta_only = len(meta_vecs) - len(set(clip_vecs) & set(meta_vecs))
    if clip_only:
        logger.warning(f"  CLIP만 있고 META 없는 VOD: {clip_only:,}건 → 제외")
    if meta_only:
        logger.warning(f"  META만 있고 CLIP 없는 VOD: {meta_only:,}건 → 제외")

    combined: dict[str, np.ndarray] = {}
    for vid in set(clip_vecs) & set(meta_vecs):
        clip_norm = _l2_normalize(clip_vecs[vid])
        meta_norm = _l2_normalize(meta_vecs[vid])
        combined[vid] = np.concatenate([clip_norm, meta_norm]).astype(np.float32)

    logger.info(f"  VOD 결합 임베딩 완료: {len(combined):,}건 (896차원)")
    return combined
