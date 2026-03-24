"""tests/test_data_loader.py — data_loader 단위 테스트"""

import sys
from pathlib import Path
import numpy as np
import pytest
from scipy.sparse import csr_matrix

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.data_loader import load_matrix


def _make_conn_stub(rows):
    """watch_history 쿼리 결과를 rows로 반환하는 stub connection."""
    class CursorStub:
        def __init__(self):
            self._rows = rows
        def execute(self, *a, **kw): pass
        def fetchall(self): return self._rows
        def close(self): pass

    class ConnStub:
        def cursor(self): return CursorStub()

    return ConnStub()


def test_matrix_shape():
    rows = [
        ("user1", "vod1", 0.5),
        ("user1", "vod2", 1.0),
        ("user2", "vod1", 0.8),
    ]
    conn = _make_conn_stub(rows)
    mat, u_enc, i_enc, u_dec, i_dec = load_matrix(conn, alpha=40)

    assert mat.shape == (2, 2)
    assert mat.nnz == 3


def test_encoder_consistency():
    rows = [
        ("userA", "vodX", 0.5),
        ("userB", "vodY", 1.0),
        ("userA", "vodY", 0.3),
    ]
    conn = _make_conn_stub(rows)
    mat, u_enc, i_enc, u_dec, i_dec = load_matrix(conn, alpha=40)

    assert len(u_enc) == 2
    assert len(i_enc) == 2
    for idx, uid in u_dec.items():
        assert u_enc[uid] == idx
    for idx, vid in i_dec.items():
        assert i_enc[vid] == idx


def test_confidence_values():
    alpha = 40
    rows = [("u1", "v1", 0.5)]
    conn = _make_conn_stub(rows)
    mat, *_ = load_matrix(conn, alpha=alpha)

    expected = 1.0 + alpha * 0.5
    assert abs(mat[0, 0] - expected) < 1e-5
