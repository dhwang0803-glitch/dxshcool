"""
인기 VOD 집계 로직 (import 전용, 직접 실행 X)
"""
from datetime import date

import pandas as pd

TARGET_GENRES = ["영화", "드라마", "예능", "애니"]


def load_vod_data(conn) -> pd.DataFrame:
    """vod 테이블에서 필요한 컬럼 로드"""
    query = """
        SELECT full_asset_id, genre, ct_cl, rating, release_date, series_nm
        FROM public.vod
    """
    return pd.read_sql(query, conn)


def aggregate_by_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    series_nm 기준 시리즈 집약.
    - series_nm NULL: 개별 VOD 그대로 처리
    - series_nm 있음: 시리즈 단위로 1개로 집약
      - rating: 시리즈 내 에피소드 평균
      - release_date: 시리즈 내 가장 최신 에피소드 기준
      - genre, ct_cl: 시리즈 내 첫 번째 값 사용
    """
    no_series = df[df["series_nm"].isna()].copy()

    has_series = df[df["series_nm"].notna()].copy()
    if has_series.empty:
        return no_series.reset_index(drop=True)

    agg = has_series.groupby("series_nm").agg(
        full_asset_id=("full_asset_id", "first"),
        genre=("genre", "first"),
        ct_cl=("ct_cl", "first"),
        rating=("rating", "mean"),
        release_date=("release_date", "max"),
    ).reset_index()  # series_nm 컬럼 유지

    return pd.concat([no_series, agg], ignore_index=True)


def calc_popularity_score(
    df: pd.DataFrame,
    rating_weight: float = 0.6,
    recency_weight: float = 0.4,
) -> pd.DataFrame:
    """
    인기 점수 계산.
    score = rating_weight * norm(rating) + recency_weight * recency_score(release_date)
    """
    df = df.copy()
    df["rating"] = df["rating"].fillna(0)

    # release_date → 숫자 변환 (일수 기준)
    today = pd.Timestamp(date.today())
    df["release_date"] = pd.to_datetime(df["release_date"], errors="coerce")
    df["release_days"] = (today - df["release_date"]).dt.days
    df["release_days"] = df["release_days"].fillna(df["release_days"].max())

    # 최신일수록 높은 점수: days가 작을수록 recency 높음 → 역수 정규화
    df["norm_rating"] = _minmax_norm(df["rating"])
    df["norm_recency"] = 1 - _minmax_norm(df["release_days"])  # 최신=1, 오래됨=0

    df["score"] = rating_weight * df["norm_rating"] + recency_weight * df["norm_recency"]

    return df


def _minmax_norm(series: pd.Series) -> pd.Series:
    mn, mx = series.min(), series.max()
    if mx == mn:
        return pd.Series(0.0, index=series.index)
    return (series - mn) / (mx - mn)


def get_top_n_by_genre(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    고정 4개 장르(영화/드라마/예능/애니)별 Top-N VOD 추출.
    슬래시(/) 구분 다중 장르는 explode로 각 장르에 개별 등록.
    """
    exploded = (
        df.assign(genre=df["genre"].str.split("/"))
        .explode("genre")
    )
    exploded["genre"] = exploded["genre"].str.strip()

    # 고정 4개 장르만 필터
    exploded = exploded[exploded["genre"].isin(TARGET_GENRES)]

    result = (
        exploded
        .sort_values("score", ascending=False)
        .groupby("genre", group_keys=False)
        .head(top_n)
    )
    result = result.copy()
    result["rank"] = result.groupby("genre").cumcount() + 1
    result = result.rename(columns={"full_asset_id": "vod_id_fk"})

    return result[["genre", "vod_id_fk", "rank", "score"]].rename(
        columns={"genre": "category_value"}
    )


def build_recommendations(df: pd.DataFrame, top_n: int = 20) -> pd.DataFrame:
    """
    장르별 Top-N 추천 결과 생성.
    출력: genre, rank, vod_id_fk, score, recommendation_type
    """
    result = get_top_n_by_genre(df, top_n)
    result = result.copy()
    result["recommendation_type"] = "POPULAR"

    return result[["category_value", "rank", "vod_id_fk", "score", "recommendation_type"]]
