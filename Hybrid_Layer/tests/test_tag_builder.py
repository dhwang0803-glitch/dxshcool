"""Phase 1 단위 테스트: VOD 태그 추출 로직."""

import pytest

from Hybrid_Layer.src.tag_builder import (
    extract_tags_from_row,
    normalize_rating,
    parse_cast,
    parse_director,
)


class TestParseCast:
    def test_json_array(self):
        assert parse_cast('["최불암", "김혜자"]') == ["최불암", "김혜자"]

    def test_empty(self):
        assert parse_cast(None) == []
        assert parse_cast("") == []

    def test_invalid_json(self):
        assert parse_cast("not json") == []

    def test_strips_whitespace(self):
        assert parse_cast('[" 홍길동 "]') == ["홍길동"]

    def test_filters_empty_strings(self):
        assert parse_cast('["홍길동", "", null]') == ["홍길동"]


class TestParseDirector:
    def test_single(self):
        assert parse_director("봉준호") == ["봉준호"]

    def test_multi(self):
        assert parse_director("Lee Jae-jin, 김형민") == ["Lee Jae-jin", "김형민"]

    def test_empty(self):
        assert parse_director(None) == []
        assert parse_director("") == []


class TestNormalizeRating:
    def test_numeric(self):
        assert normalize_rating("15") == "15세이상관람가"
        assert normalize_rating("12") == "12세이상관람가"
        assert normalize_rating("19") == "청소년관람불가"

    def test_already_normalized(self):
        assert normalize_rating("전체관람가") == "전체관람가"
        assert normalize_rating("15세이상관람가") == "15세이상관람가"

    def test_partial(self):
        assert normalize_rating("15세이상") == "15세이상관람가"
        assert normalize_rating("12세이상") == "12세이상관람가"

    def test_empty(self):
        assert normalize_rating(None) is None
        assert normalize_rating("") is None


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
        tags = extract_tags_from_row(row)

        categories = {t[1] for t in tags}
        assert categories == {"director", "actor_lead", "actor_guest", "genre", "genre_detail", "rating"}

        # director
        directors = [t for t in tags if t[1] == "director"]
        assert len(directors) == 1
        assert directors[0] == ("V001", "director", "봉준호", 1.0)

        # actor_lead (주연)
        leads = {t[2] for t in tags if t[1] == "actor_lead"}
        assert leads == {"송강호", "최우식"}

        # actor_guest (게스트)
        guests = {t[2] for t in tags if t[1] == "actor_guest"}
        assert guests == {"박소담"}

        # rating normalized
        ratings = [t for t in tags if t[1] == "rating"]
        assert ratings[0][2] == "15세이상관람가"

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
        tags = extract_tags_from_row(row)
        assert len(tags) == 1
        assert tags[0] == ("V002", "genre", "액션/모험", 1.0)

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
        tags = extract_tags_from_row(row)
        assert tags == []
