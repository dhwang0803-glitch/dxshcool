"""
STEP 2: ALS 모델 학습 및 추천 생성
"""

import logging
import implicit
from scipy.sparse import csr_matrix

log = logging.getLogger(__name__)


def train(mat: csr_matrix, factors: int = 128, iterations: int = 20,
          regularization: float = 0.01) -> implicit.als.AlternatingLeastSquares:
    """
    ALS 학습.
    implicit은 item×user 행렬을 입력으로 받으므로 mat.T 전달.
    """
    log.info("ALS 학습 시작 (factors=%d, iterations=%d, regularization=%.4f)",
             factors, iterations, regularization)

    model = implicit.als.AlternatingLeastSquares(
        factors=factors,
        iterations=iterations,
        regularization=regularization,
        use_gpu=False,
    )
    model.fit(mat.tocsr())
    log.info("ALS 학습 완료")
    return model


def recommend_all(model, mat: csr_matrix, top_k: int = 20) -> list:
    """
    전체 유저 Top-K 추천 생성.

    Returns:
        List of (user_idx, item_indices, scores)
    """
    log.info("추천 생성 중 (top_k=%d, 유저 수=%d)...", top_k, mat.shape[0])
    user_ids = list(range(mat.shape[0]))
    item_indices, scores = model.recommend(
        user_ids,
        mat[user_ids],
        N=top_k,
        filter_already_liked_items=True,
    )
    log.info("추천 생성 완료")
    return user_ids, item_indices, scores
