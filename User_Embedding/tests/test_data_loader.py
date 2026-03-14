"""
PLAN_01: data_loader.py 단위 테스트

실제 DB 연결 없이 psycopg2 커서를 mock으로 대체.
"""
import sys
import os
import pytest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from data_loader import load_watch_history


# ---------------------------------------------------------------------------
# 헬퍼: mock cursor 생성
# ---------------------------------------------------------------------------

def _make_row(user_id_fk, vod_id_fk, completion_rate):
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "user_id_fk": user_id_fk,
        "vod_id_fk": vod_id_fk,
        "completion_rate": completion_rate,
    }[key]
    return row


def _make_conn(rows: list) -> MagicMock:
    """mock conn — cursor context manager가 rows를 순회하도록 설정."""
    cur = MagicMock()
    cur.__iter__ = MagicMock(return_value=iter(rows))
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.itersize = 50_000

    conn = MagicMock()
    conn.cursor = MagicMock(return_value=cur)
    return conn, cur


# ---------------------------------------------------------------------------
# 정상 흐름
# ---------------------------------------------------------------------------

class TestLoadWatchHistoryNormal:

    def test_returns_correct_structure(self):
        rows = [
            _make_row("user_A", "vod_1", 0.8),
            _make_row("user_A", "vod_2", 0.5),
            _make_row("user_B", "vod_1", 1.0),
        ]
        conn, _ = _make_conn(rows)
        result = load_watch_history(conn)

        assert set(result.keys()) == {"user_A", "user_B"}
        assert ("vod_1", 0.8) in result["user_A"]
        assert ("vod_2", 0.5) in result["user_A"]
        assert result["user_B"] == [("vod_1", 1.0)]

    def test_completion_rate_cast_to_float(self):
        rows = [_make_row("user_A", "vod_1", "0.75")]  # 문자열로 들어올 경우
        conn, _ = _make_conn(rows)
        result = load_watch_history(conn)

        _, rate = result["user_A"][0]
        assert isinstance(rate, float)
        assert rate == 0.75

    def test_empty_table_returns_empty_dict(self):
        conn, _ = _make_conn([])
        result = load_watch_history(conn)
        assert result == {}

    def test_single_user_multiple_vods(self):
        rows = [_make_row("user_X", f"vod_{i}", 0.1 * i) for i in range(1, 6)]
        conn, _ = _make_conn(rows)
        result = load_watch_history(conn)

        assert len(result["user_X"]) == 5


# ---------------------------------------------------------------------------
# user_limit (파이럿 모드)
# ---------------------------------------------------------------------------

class TestLoadWatchHistoryPilot:

    def test_pilot_passes_limit_to_query(self):
        conn, cur = _make_conn([])
        load_watch_history(conn, user_limit=50)

        executed_sql = cur.execute.call_args[0][0]
        assert "LIMIT" in executed_sql
        assert cur.execute.call_args[0][1] == (50,)

    def test_pilot_uses_join_subquery(self):
        conn, cur = _make_conn([])
        load_watch_history(conn, user_limit=10)

        sql = cur.execute.call_args[0][0]
        assert "JOIN" in sql
        assert "DISTINCT" in sql


# ---------------------------------------------------------------------------
# user_id (단일 유저 모드)
# ---------------------------------------------------------------------------

class TestLoadWatchHistoryUserID:

    def test_single_user_query_uses_where_clause(self):
        rows = [_make_row("user_Z", "vod_99", 0.9)]
        conn, cur = _make_conn(rows)
        load_watch_history(conn, user_id="user_Z")

        sql = cur.execute.call_args[0][0]
        assert "user_id_fk = %s" in sql
        assert cur.execute.call_args[0][1] == ("user_Z",)

    def test_single_user_result_contains_only_that_user(self):
        rows = [
            _make_row("user_Z", "vod_1", 0.5),
            _make_row("user_Z", "vod_2", 0.9),
        ]
        conn, _ = _make_conn(rows)
        result = load_watch_history(conn, user_id="user_Z")

        assert list(result.keys()) == ["user_Z"]
        assert len(result["user_Z"]) == 2


# ---------------------------------------------------------------------------
# server-side cursor 설정
# ---------------------------------------------------------------------------

class TestServerSideCursor:

    def test_itersize_is_set(self):
        conn, cur = _make_conn([])
        load_watch_history(conn)
        assert cur.itersize == 50_000

    def test_named_cursor_used(self):
        conn, _ = _make_conn([])
        load_watch_history(conn)
        # 첫 번째 인자가 커서 이름 문자열인지 확인
        cursor_name = conn.cursor.call_args[0][0]
        assert cursor_name == "watch_history_cursor"
