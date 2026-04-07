"""HybridBase 공통 메서드 단위 테스트."""

from Hybrid_Layer.src.base import HybridBase


class TestIsTestFilter:
    def test_test_mode_true(self):
        result = HybridBase.is_test_filter("u", True)
        assert result == "AND u.is_test = TRUE"

    def test_test_mode_false(self):
        result = HybridBase.is_test_filter("u", False)
        assert result == "AND u.is_test = FALSE"

    def test_different_alias(self):
        assert "u2.is_test" in HybridBase.is_test_filter("u2", True)


class TestBatchUpsert:
    def test_empty_rows(self):
        """빈 리스트 시 0 반환, DB 호출 없음."""
        result = HybridBase.batch_upsert(
            conn=None,  # 빈 리스트면 루프 진입 안 함
            sql_template="INSERT INTO t VALUES {args}",
            rows=[],
            format_str="(%s)",
        )
        assert result == 0


class TestClassHierarchy:
    def test_all_services_inherit_base(self):
        from Hybrid_Layer.src.tag_builder import TagBuilder
        from Hybrid_Layer.src.preference_builder import PreferenceBuilder
        from Hybrid_Layer.src.reranker import Reranker
        from Hybrid_Layer.src.shelf_builder import ShelfBuilder

        for cls in [TagBuilder, PreferenceBuilder, Reranker, ShelfBuilder]:
            assert issubclass(cls, HybridBase), f"{cls.__name__} must inherit HybridBase"

    def test_get_conn_is_static(self):
        assert callable(HybridBase.get_conn)

    def test_is_test_filter_is_static(self):
        assert callable(HybridBase.is_test_filter)
