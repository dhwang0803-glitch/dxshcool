"""
PLAN_03: user_embedder.py 단위 테스트

DB 의존 없음 — 순수 numpy 연산 검증.
"""
import sys
import os
import pytest
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from user_embedder import build_user_embeddings, _build_user_vector

DIM = 896


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _rand_unit_vec(dim: int = DIM, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim).astype(np.float32)
    return v / np.linalg.norm(v)


# ---------------------------------------------------------------------------
# _build_user_vector: 단일 유저 벡터
# ---------------------------------------------------------------------------

class TestBuildUserVector:

    def test_returns_none_when_no_matching_vods(self):
        items = [("vod_X", 0.8), ("vod_Y", 0.5)]
        vod_vectors = {"vod_Z": _rand_unit_vec()}
        vec, count = _build_user_vector(items, vod_vectors)
        assert vec is None
        assert count == 0

    def test_returns_none_for_empty_items(self):
        vec, count = _build_user_vector([], {"vod_1": _rand_unit_vec()})
        assert vec is None
        assert count == 0

    def test_output_shape_is_896(self):
        items = [("vod_1", 0.8)]
        vod_vectors = {"vod_1": _rand_unit_vec(seed=1)}
        vec, count = _build_user_vector(items, vod_vectors)
        assert vec.shape == (DIM,)

    def test_output_is_l2_normalized(self):
        items = [("vod_1", 0.5), ("vod_2", 0.5)]
        vod_vectors = {
            "vod_1": _rand_unit_vec(seed=1),
            "vod_2": _rand_unit_vec(seed=2),
        }
        vec, _ = _build_user_vector(items, vod_vectors)
        assert abs(np.linalg.norm(vec) - 1.0) < 1e-5

    def test_vod_count_matches_matched_vods(self):
        items = [("vod_1", 0.8), ("vod_2", 0.5), ("vod_missing", 1.0)]
        vod_vectors = {
            "vod_1": _rand_unit_vec(seed=1),
            "vod_2": _rand_unit_vec(seed=2),
        }
        _, count = _build_user_vector(items, vod_vectors)
        assert count == 2  # vod_missing 제외

    def test_single_vod_result_equals_that_vod_vector(self):
        v = _rand_unit_vec(seed=42)
        items = [("vod_1", 0.9)]
        vod_vectors = {"vod_1": v}
        vec, _ = _build_user_vector(items, vod_vectors)
        # 단일 VOD → 가중 평균 = 그 벡터 자체 (L2 정규화 후)
        np.testing.assert_allclose(vec, v / np.linalg.norm(v), atol=1e-5)

    def test_weighted_average_is_not_simple_mean(self):
        """높은 completion_rate VOD가 결과 벡터에 더 많이 반영되어야 한다."""
        v1 = np.zeros(DIM, dtype=np.float32)
        v1[0] = 1.0  # unit vec, dim 0 방향
        v2 = np.zeros(DIM, dtype=np.float32)
        v2[1] = 1.0  # unit vec, dim 1 방향

        # vod_1: rate=0.9 (v1 방향 강), vod_2: rate=0.1
        items = [("vod_1", 0.9), ("vod_2", 0.1)]
        vod_vectors = {"vod_1": v1, "vod_2": v2}
        vec, _ = _build_user_vector(items, vod_vectors)

        # dim 0 성분이 dim 1 성분보다 커야 함
        assert vec[0] > vec[1]

    def test_equal_weights_approximate_mean_direction(self):
        v1 = np.zeros(DIM, dtype=np.float32); v1[0] = 1.0
        v2 = np.zeros(DIM, dtype=np.float32); v2[1] = 1.0
        items = [("vod_1", 0.5), ("vod_2", 0.5)]
        vod_vectors = {"vod_1": v1, "vod_2": v2}
        vec, _ = _build_user_vector(items, vod_vectors)
        # 동일 가중치 → dim 0 ≈ dim 1
        assert abs(vec[0] - vec[1]) < 1e-5


# ---------------------------------------------------------------------------
# build_user_embeddings: 전체 유저 처리
# ---------------------------------------------------------------------------

class TestBuildUserEmbeddings:

    def setup_method(self):
        self.vod_vectors = {
            "vod_1": _rand_unit_vec(seed=1),
            "vod_2": _rand_unit_vec(seed=2),
            "vod_3": _rand_unit_vec(seed=3),
        }

    def test_returns_two_dicts(self):
        history = {"user_A": [("vod_1", 0.8)]}
        result = build_user_embeddings(history, self.vod_vectors)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_user_with_matching_vods_included(self):
        history = {"user_A": [("vod_1", 0.8), ("vod_2", 0.5)]}
        user_vectors, vod_counts = build_user_embeddings(history, self.vod_vectors)
        assert "user_A" in user_vectors
        assert vod_counts["user_A"] == 2

    def test_user_with_no_matching_vods_excluded(self):
        history = {
            "user_A": [("vod_1", 0.8)],
            "user_B": [("vod_missing", 1.0)],
        }
        user_vectors, _ = build_user_embeddings(history, self.vod_vectors)
        assert "user_A" in user_vectors
        assert "user_B" not in user_vectors

    def test_all_users_no_matching_vods_returns_empty(self):
        history = {
            "user_A": [("vod_X", 1.0)],
            "user_B": [("vod_Y", 0.5)],
        }
        user_vectors, vod_counts = build_user_embeddings(history, self.vod_vectors)
        assert user_vectors == {}
        assert vod_counts == {}

    def test_empty_history_returns_empty(self):
        user_vectors, vod_counts = build_user_embeddings({}, self.vod_vectors)
        assert user_vectors == {}
        assert vod_counts == {}

    def test_all_output_vectors_are_l2_normalized(self):
        history = {
            "user_A": [("vod_1", 0.8), ("vod_2", 0.3)],
            "user_B": [("vod_2", 0.5), ("vod_3", 0.9)],
        }
        user_vectors, _ = build_user_embeddings(history, self.vod_vectors)
        for uid, vec in user_vectors.items():
            assert abs(np.linalg.norm(vec) - 1.0) < 1e-5, f"{uid} magnitude != 1.0"

    def test_all_output_vectors_are_896_dim(self):
        history = {
            "user_A": [("vod_1", 1.0)],
            "user_B": [("vod_2", 0.7)],
        }
        user_vectors, _ = build_user_embeddings(history, self.vod_vectors)
        for vec in user_vectors.values():
            assert vec.shape == (DIM,)

    def test_vod_counts_match_number_of_matched_vods(self):
        history = {
            "user_A": [("vod_1", 0.8), ("vod_2", 0.3), ("vod_missing", 1.0)],
        }
        _, vod_counts = build_user_embeddings(history, self.vod_vectors)
        # vod_missing은 vod_vectors에 없으므로 카운트 2
        assert vod_counts["user_A"] == 2

    def test_multiple_users_independent_results(self):
        """두 유저가 같은 VOD를 보더라도 가중치가 다르면 벡터가 다를 수 있다."""
        history = {
            "user_A": [("vod_1", 0.9), ("vod_2", 0.1)],
            "user_B": [("vod_1", 0.1), ("vod_2", 0.9)],
        }
        user_vectors, _ = build_user_embeddings(history, self.vod_vectors)
        # 두 유저 벡터가 완전히 같지 않아야 함
        assert not np.allclose(user_vectors["user_A"], user_vectors["user_B"])
