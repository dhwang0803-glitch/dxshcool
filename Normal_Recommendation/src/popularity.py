"""
인기 VOD 집계 로직 (import 전용, 직접 실행 X)

NOTE: tmdb_vote_average, tmdb_vote_count 컬럼은 Database_Design 마이그레이션 완료 후 사용 가능.
      마이그레이션 전까지 해당 컬럼이 DB에 없으면 실행 불가.
"""
import math
from datetime import date

import pandas as pd

TARGET_GENRES = ["영화", "TV드라마", "TV 연예/오락", "TV애니메이션"]

# ── 파라미터 기본값 (recommend_config.yaml과 동기화) ───────────────────
WARM_THRESHOLD      = 10   # 시청 이력 >= 10건이면 warm stage
QUALITY_MIN_WC      = 5    # quality 계산 최소 시청 수
VC_CREDIBILITY_CAP  = 10   # vote_count 신뢰도 댐핑 상한 (한국 로컬 영화 저투표수 불이익 완화: 50→10)


def load_vod_data(conn) -> pd.DataFrame:
    """vod 테이블에서 필요한 컬럼 로드 (tmdb 컬럼 포함)"""
    query = """
        SELECT full_asset_id, genre, ct_cl, release_date, series_nm,
               tmdb_vote_average, tmdb_vote_count
        FROM public.vod
    """
    return pd.read_sql(query, conn)


def aggregate_by_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    series_nm 기준 시리즈 집약.
    - series_nm NULL: 개별 VOD 그대로 처리
    - series_nm 있음: 시리즈 단위로 1개로 집약
      - tmdb_vote_average: 에피소드 평균
      - tmdb_vote_count: 에피소드 합산 (시리즈 전체 평가 수)
      - release_date: 시리즈 내 가장 최신 에피소드 기준
      - genre, ct_cl: 시리즈 내 첫 번째 값 사용
    """
    no_series = df[df["series_nm"].isna()].copy()

    has_series = df[df["series_nm"].notna()].copy()
    if has_series.empty:
        return no_series.reset_index(drop=True)

    has_series["release_date"] = pd.to_datetime(has_series["release_date"], errors="coerce")

    agg = has_series.groupby("series_nm").agg(
        full_asset_id=("full_asset_id", "first"),
        genre=("genre", "first"),
        ct_cl=("ct_cl", "first"),
        release_date=("release_date", "max"),
        tmdb_vote_average=("tmdb_vote_average", "mean"),
        tmdb_vote_count=("tmdb_vote_count", "sum"),
    ).reset_index()  # series_nm 컬럼 유지

    return pd.concat([no_series, agg], ignore_index=True)


def calc_vote_score(df: pd.DataFrame, vc_credibility_cap: int = VC_CREDIBILITY_CAP) -> pd.Series:
    """
    TMDB 평점 기반 vote_score 계산.
    vc_credibility로 소수 고평가 과대평가 방지.
    """
    va = df["tmdb_vote_average"].fillna(0)
    vc = df["tmdb_vote_count"].fillna(0)

    max_vc = vc.max()
    if max_vc == 0:
        return pd.Series(0.0, index=df.index)

    vc_credibility = vc.clip(upper=vc_credibility_cap) / vc_credibility_cap
    log_vc = vc.apply(lambda x: math.log(x + 1))
    log_max_vc = math.log(max_vc + 1)

    return (va / 10) * (log_vc / log_max_vc) * vc_credibility


def calc_freshness(df: pd.DataFrame) -> pd.Series:
    """
    최신성 점수: 출시일부터 1년간 1.0 -> 0.0 선형 감쇄.
    release_date NULL이면 0.
    """
    today = pd.Timestamp(date.today())
    release = pd.to_datetime(df["release_date"], errors="coerce")
    days_elapsed = (today - release).dt.days
    return (1 - days_elapsed / 365).clip(lower=0).fillna(0)


def calc_watch_heat(df: pd.DataFrame, watch_stats: pd.DataFrame) -> pd.Series:
    """
    자체 인기 점수: 최근 7일 시청 수 / 전체 평균, 상한 5배 후 정규화.
    watch_stats 필요 컬럼: vod_id_fk, watch_count_7d
    """
    merged = df[["full_asset_id"]].merge(
        watch_stats[["vod_id_fk", "watch_count_7d"]],
        left_on="full_asset_id", right_on="vod_id_fk",
        how="left",
    )
    watch_count_7d = merged["watch_count_7d"].fillna(0)

    avg_7d = watch_count_7d[watch_count_7d > 0].mean()
    if pd.isna(avg_7d) or avg_7d == 0:
        return pd.Series(0.0, index=df.index)

    heat = (watch_count_7d / avg_7d).clip(upper=5.0) / 5.0
    heat.index = df.index
    return heat


def calc_quality(
    df: pd.DataFrame,
    watch_stats: pd.DataFrame,
    quality_min_wc: int = QUALITY_MIN_WC,
) -> pd.Series:
    """
    자체 품질 점수: avg(completion_rate) x avg(satisfaction).
    watch_count < quality_min_wc이면 0.
    watch_stats 필요 컬럼: vod_id_fk, watch_count, avg_completion_rate, avg_satisfaction
    """
    merged = df[["full_asset_id"]].merge(
        watch_stats[["vod_id_fk", "watch_count", "avg_completion_rate", "avg_satisfaction"]],
        left_on="full_asset_id", right_on="vod_id_fk",
        how="left",
    )
    watch_count = merged["watch_count"].fillna(0)
    quality = (merged["avg_completion_rate"].fillna(0) * merged["avg_satisfaction"].fillna(0))
    quality = quality.where(watch_count >= quality_min_wc, other=0.0)
    quality.index = df.index
    return quality


def calc_popularity_score(
    df: pd.DataFrame,
    watch_stats: pd.DataFrame,
    cfg: dict,
) -> pd.DataFrame:
    """
    2단계 인기 점수 계산 (cold/warm/blend).

    cfg 키:
        warm_threshold, quality_min_wc, vc_credibility_cap
        cold_vote_weight, cold_freshness_weight
        warm_watch_heat_weight, warm_quality_weight, warm_vote_weight, warm_freshness_weight
    """
    df = df.copy()

    warm_threshold     = cfg.get("warm_threshold",          WARM_THRESHOLD)
    quality_min_wc     = cfg.get("quality_min_wc",          QUALITY_MIN_WC)
    vc_credibility_cap = cfg.get("vc_credibility_cap",      VC_CREDIBILITY_CAP)

    cold_v  = cfg.get("cold_vote_weight",          0.65)
    cold_f  = cfg.get("cold_freshness_weight",     0.35)
    warm_wh = cfg.get("warm_watch_heat_weight",    0.45)
    warm_q  = cfg.get("warm_quality_weight",       0.25)
    warm_v  = cfg.get("warm_vote_weight",          0.15)
    warm_f  = cfg.get("warm_freshness_weight",     0.15)

    df["vote_score"] = calc_vote_score(df, vc_credibility_cap)
    df["freshness"]  = calc_freshness(df)
    df["watch_heat"] = calc_watch_heat(df, watch_stats)
    df["quality"]    = calc_quality(df, watch_stats, quality_min_wc)

    # watch_count 병합 (blend 계산용)
    merged_wc = df[["full_asset_id"]].merge(
        watch_stats[["vod_id_fk", "watch_count"]],
        left_on="full_asset_id", right_on="vod_id_fk",
        how="left",
    )
    watch_count = merged_wc["watch_count"].fillna(0).values

    score_cold = cold_v  * df["vote_score"] + cold_f * df["freshness"]
    score_warm = (warm_wh * df["watch_heat"]
                + warm_q  * df["quality"]
                + warm_v  * df["vote_score"]
                + warm_f  * df["freshness"])

    blend = (pd.Series(watch_count, index=df.index) / warm_threshold).clip(upper=1.0)
    df["score"] = (1 - blend) * score_cold + blend * score_warm

    return df


def get_top_n_by_genre(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    고정 4개 CT_CL(영화/TV드라마/TV 연예/오락/TV애니메이션)별 Top-N VOD 추출.
    ct_cl은 단일 값이므로 explode 불필요.
    """
    filtered = df[df["ct_cl"].isin(TARGET_GENRES)].copy()

    result = (
        filtered
        .sort_values("score", ascending=False)
        .groupby("ct_cl", group_keys=False)
        .head(top_n)
    )
    result = result.copy()
    result["rank"] = result.groupby("ct_cl").cumcount() + 1
    result = result.rename(columns={"full_asset_id": "vod_id_fk"})

    return result[["ct_cl", "vod_id_fk", "rank", "score"]]


def build_recommendations(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    CT_CL별 Top-N 추천 결과 생성.
    출력: ct_cl, rank, vod_id_fk, score, recommendation_type
    """
    result = get_top_n_by_genre(df, top_n)
    result = result.copy()
    result["recommendation_type"] = "POPULAR"

    return result[["ct_cl", "rank", "vod_id_fk", "score", "recommendation_type"]]
