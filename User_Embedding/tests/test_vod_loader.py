"""
PLAN_02: vod_embedding_loader.py 단위 테스트

실제 DB 연결 없이 psycopg2 커서를 mock으로 대체.
"""
import sys
import os
import pytest
import numpy as np
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from vod_embedding_loader import load_vod_combined, CLIP_DIM, META_DIM, COMBINED_DIM


# ---------------------------------------------------------------------------
# 헬퍼
# ---------------------------------------------------------------------------

def _vec_str(dim: int, val: float = 1.0) -> str:
    """dim차원 벡터를 pgvector 문자열로 반환 (L2 norm = val * sqrt(dim))."""
    v = np.full(dim, val, dtype=np.float32)
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def _make_row(vod_id_fk: str, embedding: str):
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "vod_id_fk": vod_id_fk,
        "embedding": embedding,
    }[key]
    return row


def _make_conn(clip_rows: list, meta_rows: list) -> MagicMock:
    """cursor()를 두 번 호출: 첫 번째=CLIP, 두 번째=META."""
    call_count = {"n": 0}

    def cursor_factory(**kwargs):
        cur = MagicMock()
        if call_count["n"] == 0:
            cur.__iter__ = MagicMock(return_value=iter(clip_rows))
        else:
            cur.__iter__ = MagicMock(return_value=iter(meta_rows))
        cur.__enter__ = MagicMock(return_value=cur)
        cur.__exit__ = MagicMock(return_value=False)
        call_count["n"] += 1
        return cur

    conn = MagicMock()
    conn.cursor = MagicMock(side_effect=cursor_factory)
    return conn


# ---------------------------------------------------------------------------
# 차원 검증
# ---------------------------------------------------------------------------

class TestCombinedVectorShape:

    def test_output_dim_is_896(self):
        clip_rows = [_make_row("vod_1", _vec_str(CLIP_DIM))]
        meta_rows = [_make_row("vod_1", _vec_str(META_DIM))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        assert result["vod_1"].shape == (COMBINED_DIM,)

    def test_combined_dim_constant(self):
        assert COMBINED_DIM == 896
        assert CLIP_DIM == 512
        assert META_DIM == 384

    def test_dtype_is_float32(self):
        clip_rows = [_make_row("vod_1", _vec_str(CLIP_DIM))]
        meta_rows = [_make_row("vod_1", _vec_str(META_DIM))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        assert result["vod_1"].dtype == np.float32


# ---------------------------------------------------------------------------
# L2 정규화 검증
# ---------------------------------------------------------------------------

class TestL2Normalization:

    def test_clip_part_is_l2_normalized(self):
        clip_rows = [_make_row("vod_1", _vec_str(CLIP_DIM, val=2.0))]
        meta_rows = [_make_row("vod_1", _vec_str(META_DIM, val=1.0))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        clip_part = result["vod_1"][:CLIP_DIM]
        assert abs(np.linalg.norm(clip_part) - 1.0) < 1e-5

    def test_meta_part_is_l2_normalized(self):
        clip_rows = [_make_row("vod_1", _vec_str(CLIP_DIM, val=1.0))]
        meta_rows = [_make_row("vod_1", _vec_str(META_DIM, val=3.0))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        meta_part = result["vod_1"][CLIP_DIM:]
        assert abs(np.linalg.norm(meta_part) - 1.0) < 1e-5


# ---------------------------------------------------------------------------
# inner join 동작 (한쪽만 있는 VOD 제외)
# ---------------------------------------------------------------------------

class TestInnerJoin:

    def test_vod_with_both_embeddings_included(self):
        clip_rows = [_make_row("vod_common", _vec_str(CLIP_DIM))]
        meta_rows = [_make_row("vod_common", _vec_str(META_DIM))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        assert "vod_common" in result

    def test_clip_only_vod_excluded(self):
        clip_rows = [
            _make_row("vod_common", _vec_str(CLIP_DIM)),
            _make_row("vod_clip_only", _vec_str(CLIP_DIM)),
        ]
        meta_rows = [_make_row("vod_common", _vec_str(META_DIM))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        assert "vod_clip_only" not in result
        assert "vod_common" in result

    def test_meta_only_vod_excluded(self):
        clip_rows = [_make_row("vod_common", _vec_str(CLIP_DIM))]
        meta_rows = [
            _make_row("vod_common", _vec_str(META_DIM)),
            _make_row("vod_meta_only", _vec_str(META_DIM)),
        ]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        assert "vod_meta_only" not in result
        assert "vod_common" in result

    def test_no_common_vods_returns_empty(self):
        clip_rows = [_make_row("vod_A", _vec_str(CLIP_DIM))]
        meta_rows = [_make_row("vod_B", _vec_str(META_DIM))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        assert result == {}

    def test_empty_tables_returns_empty(self):
        conn = _make_conn([], [])
        result = load_vod_combined(conn)
        assert result == {}


# ---------------------------------------------------------------------------
# asset_ids 필터링
# ---------------------------------------------------------------------------

class TestAssetIdsFilter:

    def _collect_executed_sqls(self, asset_ids=None):
        """load_vod_combined 실행 후 cursor.execute에 전달된 SQL 목록 반환."""
        executed_sqls = []

        def cursor_factory(**kwargs):
            cur = MagicMock()
            cur.__iter__ = MagicMock(return_value=iter([]))
            cur.__enter__ = MagicMock(return_value=cur)
            cur.__exit__ = MagicMock(return_value=False)

            def capture_execute(sql, *args):
                executed_sqls.append(sql)
            cur.execute = MagicMock(side_effect=capture_execute)
            return cur

        conn = MagicMock()
        conn.cursor = MagicMock(side_effect=cursor_factory)
        load_vod_combined(conn, asset_ids=asset_ids)
        return executed_sqls

    def test_with_asset_ids_uses_any_clause(self):
        sqls = self._collect_executed_sqls(asset_ids=["vod_1", "vod_2"])
        assert any("ANY" in sql for sql in sqls)

    def test_without_asset_ids_uses_full_scan(self):
        sqls = self._collect_executed_sqls(asset_ids=None)
        assert all("ANY" not in sql for sql in sqls)


# ---------------------------------------------------------------------------
# pgvector 문자열 파싱
# ---------------------------------------------------------------------------

class TestVectorParsing:

    def test_parses_pgvector_string_format(self):
        vec_str = "[0.1,0.2,0.3," + ",".join(["0.0"] * (CLIP_DIM - 3)) + "]"
        clip_rows = [_make_row("vod_1", vec_str)]
        meta_rows = [_make_row("vod_1", _vec_str(META_DIM))]
        conn = _make_conn(clip_rows, meta_rows)

        result = load_vod_combined(conn)
        assert "vod_1" in result
        assert result["vod_1"].shape == (COMBINED_DIM,)
