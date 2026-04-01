"""
Poster_Collection 클래스 구조 및 하위호환 검증 테스트.
"""
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

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


class TestThreadSafety:
    """TvingPoster 캐시의 병렬 접근 안전성 검증."""

    def test_channel_cache_concurrent_writes(self):
        """여러 스레드가 동시에 _channel_cache에 쓸 때 race condition 없음."""
        from Poster_Collection.src.tving_poster import TvingPoster

        # 테스트 전 캐시 초기화
        with TvingPoster._channel_lock:
            TvingPoster._channel_cache.clear()

        errors = []

        def _write(i):
            try:
                key = f"TEST_P{i:04d}"
                with TvingPoster._channel_lock:
                    TvingPoster._channel_cache[key] = f"CH{i}"
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as ex:
            futures = [ex.submit(_write, i) for i in range(100)]
            for f in as_completed(futures):
                f.result()

        assert len(errors) == 0
        with TvingPoster._channel_lock:
            assert len(TvingPoster._channel_cache) == 100
            # 정리
            for i in range(100):
                TvingPoster._channel_cache.pop(f"TEST_P{i:04d}", None)

    def test_index_cache_double_checked_locking(self):
        """_load_index의 double-checked locking이 정상 동작하는지 검증."""
        from Poster_Collection.src.tving_poster import TvingPoster

        # 캐시에 테스트 데이터 주입
        original = TvingPoster._index_cache
        test_data = {"test_key": [{"base_nm": "test", "season": 1}]}

        with TvingPoster._index_lock:
            TvingPoster._index_cache = test_data

        results = []

        def _load(_):
            try:
                cache = TvingPoster._load_index()
                results.append(id(cache))
            except Exception:
                pass

        with ThreadPoolExecutor(max_workers=5) as ex:
            futures = [ex.submit(_load, i) for i in range(20)]
            for f in as_completed(futures):
                f.result()

        # 모든 스레드가 동일 객체를 반환해야 함
        assert len(set(results)) == 1

        # 복원
        with TvingPoster._index_lock:
            TvingPoster._index_cache = original

    def test_has_threading_locks(self):
        """TvingPoster에 lock 속성이 존재하는지 확인."""
        from Poster_Collection.src.tving_poster import TvingPoster
        assert isinstance(TvingPoster._index_lock, type(threading.Lock()))
        assert isinstance(TvingPoster._channel_lock, type(threading.Lock()))
