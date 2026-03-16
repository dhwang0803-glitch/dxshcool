"""
src/naver_poster.py 단위 테스트.
"""
import os
import sys
import pytest
from unittest.mock import patch, MagicMock

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

from Poster_Collection.src import naver_poster


# --- _pick_best 단위 테스트 ------------------------------------------------

def _make_item(link, title="", w=100, h=150):
    return {"link": link, "title": title, "sizewidth": str(w), "sizeheight": str(h)}


class TestPickBest:
    def test_returns_none_for_empty(self):
        assert naver_poster._pick_best("드라마", []) is None

    def test_prefers_portrait(self):
        landscape = _make_item("http://a.jpg", w=200, h=100)
        portrait = _make_item("http://b.jpg", w=100, h=200)
        result = naver_poster._pick_best("드라마", [landscape, portrait])
        assert result["image_url"] == "http://b.jpg"

    def test_returns_dict_with_required_keys(self):
        items = [_make_item("http://c.jpg", w=100, h=200)]
        result = naver_poster._pick_best("테스트", items)
        assert result is not None
        assert "image_url" in result
        assert "width" in result
        assert "height" in result

    def test_skips_items_without_link(self):
        items = [{"link": "", "title": "", "sizewidth": "100", "sizeheight": "200"}]
        result = naver_poster._pick_best("테스트", items)
        assert result is None

    def test_title_match_bonus(self):
        # 같은 비율이지만 series_nm이 title에 포함된 항목 우선
        item_no_match = _make_item("http://a.jpg", title="기타영화", w=100, h=200)
        item_match = _make_item("http://b.jpg", title="우영우 포스터", w=100, h=200)
        result = naver_poster._pick_best("우영우", [item_no_match, item_match])
        assert result["image_url"] == "http://b.jpg"


# --- search() 통합 테스트 (Naver API mock) ------------------------------------

class TestSearch:
    def _make_response(self, items):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"items": items}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    @patch.dict(os.environ, {"NAVER_CLIENT_ID": "test_id", "NAVER_CLIENT_SECRET": "test_secret"})
    @patch("Poster_Collection.src.naver_poster.requests.get")
    def test_returns_best_result(self, mock_get):
        items = [_make_item("http://poster.jpg", w=100, h=200)]
        mock_get.return_value = self._make_response(items)

        result = naver_poster.search("테스트드라마")

        assert result is not None
        assert result["image_url"] == "http://poster.jpg"

    @patch.dict(os.environ, {"NAVER_CLIENT_ID": "test_id", "NAVER_CLIENT_SECRET": "test_secret"})
    @patch("Poster_Collection.src.naver_poster.requests.get")
    def test_returns_none_when_no_items(self, mock_get):
        mock_get.return_value = self._make_response([])
        result = naver_poster.search("결과없음")
        assert result is None

    @patch.dict(os.environ, {"NAVER_CLIENT_ID": "test_id", "NAVER_CLIENT_SECRET": "test_secret"})
    @patch("Poster_Collection.src.naver_poster.requests.get")
    def test_retries_on_request_exception(self, mock_get):
        import requests as req
        mock_get.side_effect = [
            req.RequestException("timeout"),
            req.RequestException("timeout"),
            self._make_response([_make_item("http://ok.jpg")]),
        ]
        with patch("Poster_Collection.src.naver_poster.time.sleep"):
            result = naver_poster.search("재시도테스트")
        assert result is not None

    @patch.dict(os.environ, {"NAVER_CLIENT_ID": "test_id", "NAVER_CLIENT_SECRET": "test_secret"})
    @patch("Poster_Collection.src.naver_poster.requests.get")
    def test_returns_none_after_max_retries(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("always fail")
        with patch("Poster_Collection.src.naver_poster.time.sleep"):
            result = naver_poster.search("항상실패")
        assert result is None

    def test_raises_when_env_missing(self):
        with patch.dict(os.environ, {"NAVER_CLIENT_ID": "", "NAVER_CLIENT_SECRET": ""}):
            # naver_poster 모듈 레벨 변수를 직접 패치
            with patch.object(naver_poster, "NAVER_CLIENT_ID", ""):
                with patch.object(naver_poster, "NAVER_CLIENT_SECRET", ""):
                    with pytest.raises(EnvironmentError):
                        naver_poster.search("테스트")
