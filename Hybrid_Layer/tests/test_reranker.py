"""Phase 3 단위 테스트: 리랭킹 스코어 로직."""

from unittest.mock import MagicMock

from Hybrid_Layer.src.reranker import rerank_user


class TestReranker:
    def _mock_cursor(self, candidates, preferences, vod_tags):
        """Mock cursor that returns different data per execute call."""
        cur = MagicMock()
        call_count = 0

        def side_effect(*args, **kwargs):
            pass

        def fetchall_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:  # _fetch_user_candidates
                return candidates
            elif call_count == 2:  # _fetch_user_preferences
                return preferences
            elif call_count == 3:  # _fetch_vod_tags
                return vod_tags
            return []

        cur.execute = MagicMock(side_effect=side_effect)
        cur.fetchall = MagicMock(side_effect=fetchall_side_effect)
        return cur

    def test_basic_reranking(self):
        candidates = [
            ("V001", 0.9, "CONTENT_BASED"),
            ("V002", 0.8, "CONTENT_BASED"),
        ]
        preferences = [
            ("director", "봉준호", 0.95),
            ("genre", "드라마", 0.8),
        ]
        vod_tags = [
            ("V001", "director", "봉준호", 1.0),
            ("V001", "genre", "드라마", 1.0),
            ("V002", "genre", "액션", 1.0),
        ]

        cur = self._mock_cursor(candidates, preferences, vod_tags)
        results = rerank_user(cur, "user1", beta=0.6, top_n=10, top_k_tags=3)

        assert len(results) == 2
        assert results[0]["rank"] == 1
        assert results[1]["rank"] == 2
        # V001 should score higher (matched director + genre)
        assert results[0]["vod_id_fk"] == "V001"

    def test_no_candidates(self):
        cur = self._mock_cursor([], [], [])
        results = rerank_user(cur, "user1")
        assert results == []

    def test_no_preferences_uses_original_score(self):
        candidates = [
            ("V001", 0.9, "CONTENT_BASED"),
            ("V002", 0.8, "CONTENT_BASED"),
        ]
        cur = self._mock_cursor(candidates, [], [])
        results = rerank_user(cur, "user1", top_n=10)

        assert len(results) == 2
        assert results[0]["score"] == 0.9
        assert results[0]["explanation_tags"] == []
