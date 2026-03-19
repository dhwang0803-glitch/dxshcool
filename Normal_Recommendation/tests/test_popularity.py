"""
pytest — Normal_Recommendation/src/popularity.py 단위 테스트
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.popularity import (
    TARGET_GENRES,
    _minmax_norm,
    aggregate_by_series,
    build_recommendations,
    calc_popularity_score,
    get_top_n_by_genre,
)


# ──────────────────────────────────────────
# 픽스처
# ──────────────────────────────────────────

@pytest.fixture
def sample_vod():
    today = pd.Timestamp(date.today())
    return pd.DataFrame({
        "full_asset_id": ["V001", "V002", "V003", "V004", "V005"],
        "genre":         ["드라마", "드라마/영화", "영화", "예능", "애니"],
        "ct_cl":         ["TV드라마", "TV드라마", "영화", "TV연예", "TV애니"],
        "rating":        [8.5, 7.0, 9.0, None, 6.5],
        "release_date":  [
            today - timedelta(days=30),
            today - timedelta(days=365),
            today - timedelta(days=10),
            today - timedelta(days=180),
            today - timedelta(days=5),
        ],
        "series_nm":     [None, "시리즈A", "시리즈A", None, None],
    })


@pytest.fixture
def scored_df(sample_vod):
    agg = aggregate_by_series(sample_vod)
    return calc_popularity_score(agg)


# ──────────────────────────────────────────
# _minmax_norm
# ──────────────────────────────────────────

class TestMinmaxNorm:
    def test_basic(self):
        s = pd.Series([0.0, 5.0, 10.0])
        result = _minmax_norm(s)
        assert result.tolist() == [0.0, 0.5, 1.0]

    def test_all_same_returns_zero(self):
        s = pd.Series([3.0, 3.0, 3.0])
        result = _minmax_norm(s)
        assert (result == 0.0).all()

    def test_single_value(self):
        s = pd.Series([42.0])
        result = _minmax_norm(s)
        assert result.iloc[0] == 0.0

    def test_output_range(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _minmax_norm(s)
        assert result.min() >= 0.0
        assert result.max() <= 1.0


# ──────────────────────────────────────────
# aggregate_by_series
# ──────────────────────────────────────────

class TestAggregateBySeriesNew:
    def test_series_grouped(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        # 시리즈A(V002, V003) → 1개로 집약
        assert len(result) == 4  # V001, 시리즈A, V004, V005

    def test_no_series_kept(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        # series_nm=None인 V001, V004, V005는 그대로 유지
        no_series = result[result["series_nm"].isna()]
        assert len(no_series) == 3

    def test_series_rating_mean(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        series_row = result[result["full_asset_id"].isin(["V002", "V003"])]
        # V002 rating=7.0, V003 rating=9.0 → 평균 8.0
        assert abs(series_row["rating"].iloc[0] - 8.0) < 0.01

    def test_series_release_date_max(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        series_row = result[~result["full_asset_id"].isin(["V001", "V004", "V005"])]
        # V003 release_date(10일 전)이 V002(365일 전)보다 최신
        assert series_row["release_date"].iloc[0] == sample_vod.loc[2, "release_date"]


# ──────────────────────────────────────────
# calc_popularity_score
# ──────────────────────────────────────────

class TestCalcPopularityScore:
    def test_score_range(self, scored_df):
        assert scored_df["score"].min() >= 0.0
        assert scored_df["score"].max() <= 1.0

    def test_missing_rating_filled_zero(self, sample_vod):
        agg = aggregate_by_series(sample_vod)
        df = calc_popularity_score(agg)
        assert df["rating"].isna().sum() == 0

    def test_recent_vod_higher_score(self, sample_vod):
        # 최신 VOD(애니, V005 5일전)가 오래된 것보다 높은 recency
        agg = aggregate_by_series(sample_vod)
        df = calc_popularity_score(agg)
        ani = df[df["full_asset_id"] == "V005"]["norm_recency"].iloc[0]
        old = df[df["full_asset_id"] == "V001"]["norm_recency"].iloc[0]
        assert ani > old

    def test_custom_weights(self, sample_vod):
        agg = aggregate_by_series(sample_vod)
        df = calc_popularity_score(agg, rating_weight=1.0, recency_weight=0.0)
        assert (df["score"] == df["norm_rating"]).all()

    def test_all_rows_returned(self, sample_vod):
        agg = aggregate_by_series(sample_vod)
        df = calc_popularity_score(agg)
        assert len(df) == len(agg)


# ──────────────────────────────────────────
# get_top_n_by_genre
# ──────────────────────────────────────────

class TestGetTopNByGenre:
    def test_only_target_genres(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        assert set(result["category_value"].unique()).issubset(set(TARGET_GENRES))

    def test_multi_genre_exploded(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        # 시리즈A는 드라마+영화 두 장르에 등장 가능
        assert len(result) >= 2

    def test_rank_starts_at_one(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        assert result["rank"].min() == 1

    def test_top_n_limit(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=1)
        assert (result.groupby("category_value")["vod_id_fk"].count() <= 1).all()

    def test_columns_present(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        for col in ["category_value", "vod_id_fk", "rank", "score"]:
            assert col in result.columns


# ──────────────────────────────────────────
# build_recommendations
# ──────────────────────────────────────────

class TestBuildRecommendations:
    def test_recommendation_type_fixed(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        assert (result["recommendation_type"] == "POPULAR").all()

    def test_required_columns(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        for col in ["category_value", "rank", "vod_id_fk", "score", "recommendation_type"]:
            assert col in result.columns

    def test_only_target_genres(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        assert set(result["category_value"].unique()).issubset(set(TARGET_GENRES))

    def test_rank_starts_at_one(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        assert result["rank"].min() == 1
