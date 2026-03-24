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


def recommend_all(model, mat: csr_matrix, top_k: int = 20,
                   raw_multiplier: int = 3) -> list:
    """
    전체 유저 Top-K 추천 생성.

    시리즈 중복 제거 후에도 top_k개를 확보하기 위해
    raw_top_k = top_k * raw_multiplier 만큼 후보를 뽑는다.

    Returns:
        List of (user_idx, item_indices, scores)
    """
    raw_top_k = min(top_k * raw_multiplier, mat.shape[1])
    log.info("추천 생성 중 (raw_top_k=%d → 시리즈 중복 제거 후 top_k=%d, 유저 수=%d)...",
             raw_top_k, top_k, mat.shape[0])
    user_ids = list(range(mat.shape[0]))
    item_indices, scores = model.recommend(
        user_ids,
        mat[user_ids],
        N=raw_top_k,
        filter_already_liked_items=True,
    )
    log.info("추천 생성 완료")
    return user_ids, item_indices, scores
