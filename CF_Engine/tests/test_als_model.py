"""tests/test_als_model.py — ALSModel 단위 테스트"""

import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import csr_matrix

implicit = pytest.importorskip("implicit")

sys.path.insert(0, ".")

from CF_Engine.src.als_model import ALSModel, als_model, train, recommend_all
from CF_Engine.src.base import CFBase


def _sample_matrix(n_users=50, n_items=30, density=0.1, seed=42):
    rng = np.random.default_rng(seed)
    data = rng.random((n_users, n_items))
    mask = rng.random((n_users, n_items)) < density
    data[~mask] = 0
    return csr_matrix(data, dtype=np.float32)


def test_train_returns_model():
    mat = _sample_matrix()
    model = ALSModel.train(mat, factors=16, iterations=3, regularization=0.01)
    assert model is not None


def test_factor_vectors_shape():
    n_users, n_items = 50, 30
    factors = 16
    mat = _sample_matrix(n_users, n_items)
    model = ALSModel.train(mat, factors=factors, iterations=3)

    assert model.user_factors.shape == (n_users, factors)
    assert model.item_factors.shape == (n_items, factors)


def test_recommend_returns_k_items():
    mat = _sample_matrix()
    model = ALSModel.train(mat, factors=16, iterations=3)
    top_k = 5
    user_ids, item_indices, scores = ALSModel.recommend_all(model, mat, top_k=top_k)

    assert len(user_ids) == mat.shape[0]
    assert item_indices.shape == (mat.shape[0], top_k)
    assert scores.shape == (mat.shape[0], top_k)


class TestALSModelClass:
    def test_inherits_base(self):
        assert issubclass(ALSModel, CFBase)

    def test_singleton(self):
        assert isinstance(als_model, ALSModel)

    def test_backward_compat_aliases(self):
        assert train is ALSModel.train
        assert recommend_all is ALSModel.recommend_all
