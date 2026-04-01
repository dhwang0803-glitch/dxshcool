"""
Poster_Collection 클래스 구조 및 하위호환 검증 테스트.
"""
import os
import sys

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

from Poster_Collection.src.base import PosterBase


class TestPosterBase:
    def test_title_similarity_identical(self):
        assert PosterBase.title_similarity("신서유기", "신서유기") == 1.0

    def test_title_similarity_empty(self):
        assert PosterBase.title_similarity("", "abc") == 0.0
        assert PosterBase.title_similarity("abc", "") == 0.0

    def test_title_similarity_partial(self):
        sim = PosterBase.title_similarity("신서유기", "신서유기2")
        assert 0.0 < sim < 1.0


class TestTMDBPosterClass:
    def test_inherits_poster_base(self):
        from Poster_Collection.src.tmdb_poster import TMDBPoster
        assert issubclass(TMDBPoster, PosterBase)

    def test_backward_compat_search(self):
        from Poster_Collection.src import tmdb_poster
        assert callable(tmdb_poster.search)

    def test_backward_compat_aliases(self):
        from Poster_Collection.src import tmdb_poster
        assert callable(tmdb_poster.search)
        assert callable(tmdb_poster._tmdb_headers)
        assert callable(tmdb_poster._tmdb_params)
        assert callable(tmdb_poster._tmdb_available)

    def test_title_similarity_contains(self):
        from Poster_Collection.src.tmdb_poster import TMDBPoster
        sim = TMDBPoster._title_similarity("abc", "xabcx")
        assert sim > 0.0

    def test_item_names(self):
        from Poster_Collection.src.tmdb_poster import TMDBPoster
        names = TMDBPoster._item_names({
            "name": "시그널",
            "original_name": "Signal",
            "title": "",
        })
        assert "시그널" in names
        assert "Signal" in names
        assert "" not in names


class TestTvingPosterClass:
    def test_inherits_poster_base(self):
        from Poster_Collection.src.tving_poster import TvingPoster
        assert issubclass(TvingPoster, PosterBase)

    def test_backward_compat_search(self):
        from Poster_Collection.src import tving_poster
        assert callable(tving_poster.search)

    def test_backward_compat_build_index(self):
        from Poster_Collection.src import tving_poster
        assert callable(tving_poster.build_index)

    def test_backward_compat_parse_season(self):
        from Poster_Collection.src import tving_poster
        assert callable(tving_poster.parse_season_from_asset_nm)

    def test_parse_season_basic(self):
        from Poster_Collection.src.tving_poster import TvingPoster
        base, season = TvingPoster.parse_season_from_asset_nm("신서유기 시즌2 01회")
        assert base == "신서유기"
        assert season == 2

    def test_parse_season_default(self):
        from Poster_Collection.src.tving_poster import TvingPoster
        base, season = TvingPoster.parse_season_from_asset_nm("윤스테이 01회")
        assert base == "윤스테이"
        assert season == 1

    def test_parse_season_from_title(self):
        from Poster_Collection.src.tving_poster import TvingPoster
        base, season = TvingPoster.parse_season_from_title("신서유기 2")
        assert base == "신서유기"
        assert season == 2


class TestOCIUploaderClass:
    def test_inherits_poster_base(self):
        from Poster_Collection.src.oci_uploader import OCIUploader
        assert issubclass(OCIUploader, PosterBase)

    def test_backward_compat_aliases(self):
        from Poster_Collection.src import oci_uploader
        assert callable(oci_uploader.build_public_url)
        assert callable(oci_uploader.upload_file)
        assert callable(oci_uploader.object_exists)

    def test_build_public_url(self):
        from Poster_Collection.src.oci_uploader import OCIUploader
        url = OCIUploader.build_public_url(
            "ap-chuncheon-1", "ns", "bucket", "test.jpg"
        )
        assert "objectstorage.ap-chuncheon-1.oraclecloud.com" in url
        assert "test.jpg" in url

    def test_content_type(self):
        from Poster_Collection.src.oci_uploader import OCIUploader
        assert OCIUploader._content_type(".jpg") == "image/jpeg"
        assert OCIUploader._content_type(".png") == "image/png"
        assert OCIUploader._content_type(".xyz") == "application/octet-stream"


class TestDBUpdaterClass:
    def test_inherits_poster_base(self):
        from Poster_Collection.src.db_updater import DBUpdater
        assert issubclass(DBUpdater, PosterBase)

    def test_backward_compat_aliases(self):
        from Poster_Collection.src import db_updater
        from Poster_Collection.src.db_updater import DBUpdater
        assert db_updater.update_poster_urls is DBUpdater.update_poster_urls
        assert db_updater.update_poster_urls_by_season is DBUpdater.update_poster_urls_by_season

    def test_update_empty_mapping(self):
        """빈 매핑이면 0을 반환하고 DB 접근 없음."""
        from Poster_Collection.src.db_updater import DBUpdater
        result = DBUpdater.update_poster_urls(None, {})
        assert result == 0
