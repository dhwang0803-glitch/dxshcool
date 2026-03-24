"""
src/image_downloader.py 단위 테스트.
"""
import os
import sys
import tempfile
import pytest
from unittest.mock import patch, MagicMock, mock_open

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

from Poster_Collection.src import image_downloader


class TestSafeFilename:
    def test_replaces_invalid_chars(self):
        result = image_downloader._safe_filename('a/b\\c:d*e?f"g<h>i|j')
        assert "/" not in result
        assert "\\" not in result
        assert ":" not in result
        assert "*" not in result

    def test_normal_id_unchanged(self):
        assert image_downloader._safe_filename("12345") == "12345"

    def test_converts_to_string(self):
        assert image_downloader._safe_filename(9999) == "9999"


class TestDownload:
    def _make_response(self, content_type="image/jpeg", content=b"FAKEJPEG"):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": content_type}
        mock_resp.raise_for_status.return_value = None
        mock_resp.iter_content.return_value = [content]
        return mock_resp

    @patch("Poster_Collection.src.image_downloader.requests.get")
    def test_saves_jpeg(self, mock_get):
        mock_get.return_value = self._make_response("image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = image_downloader.download("1001", "http://example.com/img.jpg", tmpdir)
            assert result is not None
            assert result.endswith("1001.jpg")
            assert os.path.exists(result)

    @patch("Poster_Collection.src.image_downloader.requests.get")
    def test_saves_png(self, mock_get):
        mock_get.return_value = self._make_response("image/png")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = image_downloader.download("1002", "http://example.com/img.png", tmpdir)
            assert result is not None

    @patch("Poster_Collection.src.image_downloader.requests.get")
    def test_rejects_disallowed_content_type(self, mock_get):
        mock_get.return_value = self._make_response("text/html")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = image_downloader.download("1003", "http://example.com/page.html", tmpdir)
            assert result is None
            # 파일이 남아있지 않아야 함
            assert not os.path.exists(os.path.join(tmpdir, "1003.jpg"))

    @patch("Poster_Collection.src.image_downloader.requests.get")
    def test_returns_none_on_request_failure(self, mock_get):
        import requests as req
        mock_get.side_effect = req.RequestException("connection error")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = image_downloader.download("1004", "http://bad.url/img.jpg", tmpdir)
            assert result is None

    @patch("Poster_Collection.src.image_downloader.requests.get")
    def test_creates_local_dir_if_missing(self, mock_get):
        mock_get.return_value = self._make_response("image/jpeg")
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = os.path.join(tmpdir, "new_subdir")
            result = image_downloader.download("1005", "http://example.com/img.jpg", nested)
            assert result is not None
            assert os.path.isdir(nested)

    @patch("Poster_Collection.src.image_downloader.requests.get")
    def test_content_type_with_charset(self, mock_get):
        """Content-Type: image/jpeg; charset=utf-8 같은 케이스 처리."""
        mock_get.return_value = self._make_response("image/jpeg; charset=utf-8")
        with tempfile.TemporaryDirectory() as tmpdir:
            result = image_downloader.download("1006", "http://example.com/img.jpg", tmpdir)
            assert result is not None
