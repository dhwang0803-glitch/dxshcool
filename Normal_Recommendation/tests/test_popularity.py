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
    aggregate_by_series,
    build_recommendations,
    calc_freshness,
    calc_popularity_score,
    calc_quality,
    calc_vote_score,
    calc_watch_heat,
    get_top_n_by_genre,
)

# ── 기본 설정값 ────────────────────────────────────────────────────────
DEFAULT_CFG = {
    "warm_threshold": 10,
    "quality_min_wc": 5,
    "vc_credibility_cap": 50,
    "cold_vote_weight": 0.65,
    "cold_freshness_weight": 0.35,
    "warm_watch_heat_weight": 0.45,
    "warm_quality_weight": 0.25,
    "warm_vote_weight": 0.15,
    "warm_freshness_weight": 0.15,
}


# ── 픽스처 ─────────────────────────────────────────────────────────────

@pytest.fixture
def sample_vod():
    today = pd.Timestamp(date.today())
    return pd.DataFrame({
        "full_asset_id":     ["V001", "V002", "V003", "V004", "V005"],
        "genre":             ["드라마", "드라마/영화", "영화", "예능", "애니"],
        "ct_cl":             ["TV드라마", "TV드라마", "영화", "TV 연예/오락", "TV애니메이션"],
        "release_date":      [
            today - timedelta(days=30),
            today - timedelta(days=365),
            today - timedelta(days=10),
            today - timedelta(days=180),
            today - timedelta(days=5),
        ],
        "series_nm":         [None, "시리즈A", "시리즈A", None, None],
        "tmdb_vote_average": [7.5, 8.0, 9.0, None, 6.5],
        "tmdb_vote_count":   [1000, 500, 2000, None, 300],
    })


@pytest.fixture
def sample_watch_stats():
    return pd.DataFrame({
        "vod_id_fk":            ["V001", "V002", "V004", "V005"],
        "watch_count":          [20,     3,      50,     8],
        "watch_count_7d":       [5,      1,      15,     3],
        "avg_completion_rate":  [0.8,    0.6,    0.7,    0.9],
        "avg_satisfaction":     [0.7,    0.5,    0.8,    0.85],
    })


@pytest.fixture
def agg_vod(sample_vod):
    return aggregate_by_series(sample_vod)


@pytest.fixture
def scored_df(agg_vod, sample_watch_stats):
    return calc_popularity_score(agg_vod, sample_watch_stats, DEFAULT_CFG)


# ── aggregate_by_series ────────────────────────────────────────────────

class TestAggregateBySeriesNew:
    def test_series_grouped(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        assert len(result) == 4  # V001, 시리즈A, V004, V005

    def test_no_series_kept(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        no_series = result[result["series_nm"].isna()]
        assert len(no_series) == 3

    def test_series_vote_average_mean(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        series_row = result[result["series_nm"] == "시리즈A"]
        # V002=8.0, V003=9.0 -> 평균 8.5
        assert abs(series_row["tmdb_vote_average"].iloc[0] - 8.5) < 0.01

    def test_series_vote_count_sum(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        series_row = result[result["series_nm"] == "시리즈A"]
        # V002=500, V003=2000 -> 합산 2500
        assert series_row["tmdb_vote_count"].iloc[0] == 2500

    def test_series_release_date_max(self, sample_vod):
        result = aggregate_by_series(sample_vod)
        series_row = result[result["series_nm"] == "시리즈A"]
        # V003(10일 전)이 V002(365일 전)보다 최신
        assert series_row["release_date"].iloc[0] == sample_vod.loc[2, "release_date"]


# ── calc_vote_score ────────────────────────────────────────────────────

class TestCalcVoteScore:
    def test_zero_vote_count_returns_zero(self, agg_vod):
        df = agg_vod.copy()
        df["tmdb_vote_count"] = 0
        result = calc_vote_score(df)
        assert (result == 0.0).all()

    def test_range(self, agg_vod):
        result = calc_vote_score(agg_vod)
        assert result.max() <= 1.0
        assert result.min() >= 0.0

    def test_low_vc_dampened(self):
        df = pd.DataFrame({
            "tmdb_vote_average": [10.0, 10.0],
            "tmdb_vote_count":   [1,    1000],
        })
        result = calc_vote_score(df, vc_credibility_cap=50)
        # VC=1은 VC=1000보다 훨씬 낮아야 함
        assert result.iloc[0] < result.iloc[1]

    def test_null_filled_zero(self, agg_vod):
        result = calc_vote_score(agg_vod)
        assert result.isna().sum() == 0


# ── calc_freshness ─────────────────────────────────────────────────────

class TestCalcFreshness:
    def test_range(self, agg_vod):
        result = calc_freshness(agg_vod)
        assert result.max() <= 1.0
        assert result.min() >= 0.0

    def test_over_one_year_is_zero(self):
        df = pd.DataFrame({
            "release_date": [pd.Timestamp(date.today()) - timedelta(days=400)]
        })
        result = calc_freshness(df)
        assert result.iloc[0] == 0.0

    def test_null_release_date_is_zero(self):
        df = pd.DataFrame({"release_date": [None]})
        result = calc_freshness(df)
        assert result.iloc[0] == 0.0

    def test_today_is_one(self):
        df = pd.DataFrame({"release_date": [pd.Timestamp(date.today())]})
        result = calc_freshness(df)
        assert result.iloc[0] == pytest.approx(1.0, abs=0.01)


# ── calc_watch_heat ────────────────────────────────────────────────────

class TestCalcWatchHeat:
    def test_range(self, agg_vod, sample_watch_stats):
        result = calc_watch_heat(agg_vod, sample_watch_stats)
        assert result.min() >= 0.0
        assert result.max() <= 1.0

    def test_no_watch_history_is_zero(self, agg_vod, sample_watch_stats):
        # V003은 watch_stats에 없음 -> 0
        result = calc_watch_heat(agg_vod, sample_watch_stats)
        v003_idx = agg_vod[agg_vod["full_asset_id"] == "V003"].index
        if len(v003_idx) > 0:
            assert result.loc[v003_idx[0]] == 0.0

    def test_empty_watch_stats_returns_zero(self, agg_vod):
        empty_stats = pd.DataFrame(columns=["vod_id_fk", "watch_count_7d"])
        result = calc_watch_heat(agg_vod, empty_stats)
        assert (result == 0.0).all()


# ── calc_quality ───────────────────────────────────────────────────────

class TestCalcQuality:
    def test_below_min_wc_is_zero(self, agg_vod, sample_watch_stats):
        # V002: watch_count=3 < quality_min_wc=5 -> quality=0
        result = calc_quality(agg_vod, sample_watch_stats, quality_min_wc=5)
        v002_idx = agg_vod[agg_vod["full_asset_id"] == "V002"].index
        if len(v002_idx) > 0:
            assert result.loc[v002_idx[0]] == 0.0

    def test_above_min_wc_nonzero(self, agg_vod, sample_watch_stats):
        # V001: watch_count=20 >= 5 -> quality > 0
        result = calc_quality(agg_vod, sample_watch_stats, quality_min_wc=5)
        v001_idx = agg_vod[agg_vod["full_asset_id"] == "V001"].index
        if len(v001_idx) > 0:
            assert result.loc[v001_idx[0]] > 0.0

    def test_range(self, agg_vod, sample_watch_stats):
        result = calc_quality(agg_vod, sample_watch_stats)
        assert result.min() >= 0.0
        assert result.max() <= 1.0


# ── calc_popularity_score ──────────────────────────────────────────────

class TestCalcPopularityScore:
    def test_score_range(self, scored_df):
        assert scored_df["score"].min() >= 0.0
        assert scored_df["score"].max() <= 1.0

    def test_required_columns(self, scored_df):
        for col in ["vote_score", "freshness", "watch_heat", "quality", "score"]:
            assert col in scored_df.columns

    def test_all_rows_returned(self, agg_vod, sample_watch_stats):
        result = calc_popularity_score(agg_vod, sample_watch_stats, DEFAULT_CFG)
        assert len(result) == len(agg_vod)

    def test_cold_stage_watch_heat_zero(self, agg_vod):
        empty_stats = pd.DataFrame(columns=["vod_id_fk", "watch_count",
                                            "watch_count_7d", "avg_completion_rate",
                                            "avg_satisfaction"])
        result = calc_popularity_score(agg_vod, empty_stats, DEFAULT_CFG)
        assert (result["watch_heat"] == 0.0).all()
        assert (result["quality"] == 0.0).all()

    def test_warm_stage_high_watch_count(self, agg_vod):
        stats = pd.DataFrame({
            "vod_id_fk":           agg_vod["full_asset_id"].tolist(),
            "watch_count":         [50] * len(agg_vod),
            "watch_count_7d":      [10] * len(agg_vod),
            "avg_completion_rate": [0.8] * len(agg_vod),
            "avg_satisfaction":    [0.7] * len(agg_vod),
        })
        result = calc_popularity_score(agg_vod, stats, DEFAULT_CFG)
        assert result["score"].min() >= 0.0


# ── get_top_n_by_genre ─────────────────────────────────────────────────

class TestGetTopNByGenre:
    def test_only_target_genres(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        assert set(result["ct_cl"].unique()).issubset(set(TARGET_GENRES))

    def test_rank_starts_at_one(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        assert result["rank"].min() == 1

    def test_top_n_limit(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=1)
        assert (result.groupby("ct_cl")["vod_id_fk"].count() <= 1).all()

    def test_columns_present(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        for col in ["ct_cl", "vod_id_fk", "rank", "score"]:
            assert col in result.columns

    def test_multi_genre(self, scored_df):
        result = get_top_n_by_genre(scored_df, top_n=5)
        assert len(result) >= 2


# ── build_recommendations ──────────────────────────────────────────────

class TestBuildRecommendations:
    def test_recommendation_type_fixed(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        assert (result["recommendation_type"] == "POPULAR").all()

    def test_required_columns(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        for col in ["ct_cl", "rank", "vod_id_fk", "score", "recommendation_type"]:
            assert col in result.columns

    def test_only_target_genres(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        assert set(result["ct_cl"].unique()).issubset(set(TARGET_GENRES))

    def test_rank_starts_at_one(self, scored_df):
        result = build_recommendations(scored_df, top_n=5)
        assert result["rank"].min() == 1
