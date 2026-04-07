"""Phase 1 단위 테스트: VOD 태그 추출 로직."""

import pytest

from Hybrid_Layer.src.tag_builder import (
    TagBuilder,
    tag_builder,
    extract_tags_from_row,
    normalize_rating,
    parse_cast,
    parse_director,
)


class TestParseCast:
    def test_json_array(self):
        assert TagBuilder.parse_cast('["최불암", "김혜자"]') == ["최불암", "김혜자"]

    def test_empty(self):
        assert TagBuilder.parse_cast(None) == []
        assert TagBuilder.parse_cast("") == []

    def test_invalid_json(self):
        assert TagBuilder.parse_cast("not json") == []

    def test_strips_whitespace(self):
        assert TagBuilder.parse_cast('[" 홍길동 "]') == ["홍길동"]

    def test_filters_empty_strings(self):
        assert TagBuilder.parse_cast('["홍길동", "", null]') == ["홍길동"]

    def test_backward_compat_alias(self):
        assert parse_cast('["a"]') == ["a"]


class TestParseDirector:
    def test_single(self):
        assert TagBuilder.parse_director("봉준호") == ["봉준호"]

    def test_multi(self):
        assert TagBuilder.parse_director("Lee Jae-jin, 김형민") == ["Lee Jae-jin", "김형민"]

    def test_empty(self):
        assert TagBuilder.parse_director(None) == []
        assert TagBuilder.parse_director("") == []

    def test_backward_compat_alias(self):
        assert parse_director("a") == ["a"]


class TestNormalizeRating:
    def test_numeric(self):
        assert TagBuilder.normalize_rating("15") == "15세이상관람가"
        assert TagBuilder.normalize_rating("12") == "12세이상관람가"
        assert TagBuilder.normalize_rating("19") == "청소년관람불가"

    def test_already_normalized(self):
        assert TagBuilder.normalize_rating("전체관람가") == "전체관람가"
        assert TagBuilder.normalize_rating("15세이상관람가") == "15세이상관람가"

    def test_partial(self):
        assert TagBuilder.normalize_rating("15세이상") == "15세이상관람가"
        assert TagBuilder.normalize_rating("12세이상") == "12세이상관람가"

    def test_empty(self):
        assert TagBuilder.normalize_rating(None) is None
        assert TagBuilder.normalize_rating("") is None

    def test_backward_compat_alias(self):
        assert normalize_rating("15") == "15세이상관람가"


class TestExtractTags:
    def test_full_row(self):
        row = {
            "full_asset_id": "V001",
            "director": "봉준호",
            "cast_lead": '["송강호", "최우식"]',
            "cast_guest": '["박소담"]',
            "genre": "드라마",
            "genre_detail": "무비n시리즈",
            "rating": "15",
        }
        tags = TagBuilder.extract_tags_from_row(row)

        categories = {t[1] for t in tags}
        assert "director" in categories
        assert "actor_lead" in categories
        assert "actor_guest" in categories
        assert "genre" in categories

        # director
        directors = [t for t in tags if t[1] == "director"]
        assert len(directors) == 1
        assert directors[0] == ("V001", "director", "봉준호", 0.1)

        # actor_lead (주연)
        leads = {t[2] for t in tags if t[1] == "actor_lead"}
        assert leads == {"송강호", "최우식"}

        # actor_guest (게스트)
        guests = {t[2] for t in tags if t[1] == "actor_guest"}
        assert guests == {"박소담"}

    def test_minimal_row(self):
        row = {
            "full_asset_id": "V002",
            "director": None,
            "cast_lead": None,
            "cast_guest": None,
            "genre": "액션/모험",
            "genre_detail": None,
            "rating": None,
        }
        tags = TagBuilder.extract_tags_from_row(row)
        assert len(tags) == 1
        assert tags[0] == ("V002", "genre", "액션/모험", 0.1)

    def test_empty_row(self):
        row = {
            "full_asset_id": "V003",
            "director": "",
            "cast_lead": "",
            "cast_guest": "",
            "genre": "",
            "genre_detail": "",
            "rating": "",
        }
        tags = TagBuilder.extract_tags_from_row(row)
        assert tags == []

    def test_backward_compat_alias(self):
        row = {"full_asset_id": "V004", "genre": "코미디"}
        tags = extract_tags_from_row(row)
        assert len(tags) == 1


class TestTagBuilderClass:
    """TagBuilder 클래스 구조 테스트."""

    def test_singleton_instance(self):
        assert isinstance(tag_builder, TagBuilder)

    def test_inherits_hybrid_base(self):
        from Hybrid_Layer.src.base import HybridBase
        assert issubclass(TagBuilder, HybridBase)

    def test_build_is_instance_method(self):
        from Hybrid_Layer.src.tag_builder import build_vod_tags
        assert build_vod_tags == tag_builder.build
