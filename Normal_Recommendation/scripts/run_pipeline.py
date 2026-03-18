"""
인기 VOD 추천 파이프라인 실행 스크립트

사용법:
  python scripts/run_pipeline.py                       # 조장: DB 직접 적재
  python scripts/run_pipeline.py --output parquet      # 팀원: parquet 저장
  python scripts/run_pipeline.py --dry-run             # 저장 없이 결과만 출력
"""
import argparse
import os
import sys
from datetime import date

import pandas as pd
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import get_conn, load_watch_stats
from src.popularity import (
    aggregate_by_series,
    build_recommendations,
    calc_popularity_score,
    load_vod_data,
)


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "recommend_config.yaml")
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(output_mode: str, dry_run: bool) -> None:
    cfg = load_config()
    pop_cfg = cfg["popularity"]
    exp_cfg = cfg["export"]

    print("[INFO] DB 연결 중...")
    with get_conn() as conn:
        print("[INFO] vod 테이블 로드 중...")
        vod_df = load_vod_data(conn)
        print(f"[INFO] vod: {len(vod_df):,}건")

        print("[INFO] watch_history 통계 집계 중...")
        watch_stats = load_watch_stats(conn)
        print(f"[INFO] watch_stats: {len(watch_stats):,}건")

    print("[INFO] 시리즈 단위 집약 중...")
    agg_df = aggregate_by_series(vod_df)
    print(f"[INFO] 집약 후: {len(agg_df):,}건")

    print("[INFO] 인기 점수 계산 중...")
    scored_df = calc_popularity_score(agg_df, watch_stats, pop_cfg)

    print("[INFO] 장르별 Top-N 추천 결과 생성 중...")
    result_df = build_recommendations(scored_df, top_n=pop_cfg["top_n"])
    print(f"[INFO] 추천 결과: {len(result_df):,}건")

    if dry_run:
        print("\n[DRY-RUN] 상위 10개 추천 결과:")
        print(result_df.head(10).to_string(index=False))
        return

    if output_mode == "parquet":
        _save_parquet(result_df, exp_cfg["output_dir"])
    else:
        from scripts.export_to_db import export
        with get_conn() as conn:
            export(result_df, conn)

    print("[INFO] 완료.")


def _save_parquet(df: pd.DataFrame, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    out_path = os.path.join(output_dir, f"recommendations_popular_{today}.parquet")
    df.to_parquet(out_path, index=False)
    print(f"[INFO] parquet 저장 완료: {out_path} ({len(df):,}건)")
    print("[INFO] 조장에게 파일을 전달하세요.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="인기 VOD 추천 파이프라인")
    parser.add_argument(
        "--output",
        choices=["parquet", "db"],
        default="db",
        help="출력 방식: parquet(팀원) 또는 db(조장, 기본값)",
    )
    parser.add_argument("--dry-run", action="store_true", help="저장 없이 결과만 출력")
    args = parser.parse_args()

    run(output_mode=args.output, dry_run=args.dry_run)
