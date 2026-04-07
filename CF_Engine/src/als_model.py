"""STEP 2: ALS 모델 학습 및 추천 생성."""

import logging

from scipy.sparse import csr_matrix

from CF_Engine.src.base import CFBase

log = logging.getLogger(__name__)


class ALSModel(CFBase):
    """ALS 기반 협업 필터링 모델."""

    @staticmethod
    def train(mat: csr_matrix, factors: int = 128, iterations: int = 20,
              regularization: float = 0.01):
        """ALS 학습. implicit은 item×user 행렬을 입력으로 받으므로 mat.T 전달."""
        import implicit

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

    @staticmethod
    def recommend_all(model, mat: csr_matrix, top_k: int = 20,
                      raw_multiplier: int = 3) -> tuple:
        """전체 유저 Top-K 추천 생성.

        시리즈 중복 제거 후에도 top_k개를 확보하기 위해
        raw_top_k = top_k * raw_multiplier 만큼 후보를 뽑는다.

        Returns:
            (user_ids, item_indices, scores)
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


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
als_model = ALSModel()
train = ALSModel.train
recommend_all = ALSModel.recommend_all
