"""
추천 결과 Genre Precision@k 평가

사용법:
    python Vector_Search/scripts/evaluate_precision.py
    python Vector_Search/scripts/evaluate_precision.py --sample 500
    python Vector_Search/scripts/evaluate_precision.py --parquet Vector_Search/data/recommendations_xxx.parquet

출력:
    - Genre Precision@5, @10, @20
    - ct_cl(콘텐츠 유형) Precision@5, @10, @20
    - 샘플 VOD 기준 상세 결과
"""
import argparse
import sys
from pathlib import Path

import pandas as pd
import numpy as np
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.db import get_connection

DATA_DIR = Path(__file__).parent.parent / "data"


def load_vod_meta(conn) -> pd.DataFrame:
    print("[1/3] DB에서 VOD 메타 로드 중 (genre, ct_cl, director)...")
    cur = conn.cursor()
    cur.execute("""
        SELECT full_asset_id, genre, ct_cl, director
        FROM vod
        WHERE full_asset_id IS NOT NULL
    """)
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["vod_id", "genre", "ct_cl", "director"])
    print(f"  → {len(df):,}건 로드 완료")
    return df.set_index("vod_id")


def genre_match(src_genre: str, tgt_genre: str) -> bool:
    if not src_genre or not tgt_genre:
        return False
    src_set = set(g.strip() for g in src_genre.split("/"))
    tgt_set = set(g.strip() for g in tgt_genre.split("/"))
    return bool(src_set & tgt_set)


def calc_precision_at_k(rec_df: pd.DataFrame, meta_df: pd.DataFrame, field: str, k: int, sample: int) -> float:
    # 샘플 source_id 선정
    source_ids = rec_df["source_vod_id"].unique()
    if sample and len(source_ids) > sample:
        rng = np.random.default_rng(42)
        source_ids = rng.choice(source_ids, size=sample, replace=False)

    # 샘플만 필터 후 top-k 추출 (groupby 활용)
    sampled = rec_df[rec_df["source_vod_id"].isin(source_ids)]
    top_k_df = sampled[sampled["rank"] <= k].copy()

    # 메타 join
    top_k_df["src_val"] = top_k_df["source_vod_id"].map(meta_df[field])
    top_k_df["tgt_val"] = top_k_df["vod_id_fk"].map(meta_df[field])
    top_k_df = top_k_df.dropna(subset=["src_val", "tgt_val"])

    if field == "genre":
        top_k_df["hit"] = top_k_df.apply(
            lambda r: 1 if genre_match(r["src_val"], r["tgt_val"]) else 0, axis=1
        )
    else:
        top_k_df["hit"] = (top_k_df["src_val"] == top_k_df["tgt_val"]).astype(int)

    precision_per_src = top_k_df.groupby("source_vod_id")["hit"].mean()
    return float(precision_per_src.mean()) if len(precision_per_src) > 0 else 0.0


def main():
    parser = argparse.ArgumentParser(description="Genre Precision@k 평가")
    parser.add_argument("--parquet", default=None, help="평가할 parquet 경로")
    parser.add_argument("--sample", type=int, default=1000, help="샘플 VOD 수 (기본 1000)")
    args = parser.parse_args()

    # parquet 자동 탐색
    if args.parquet:
        parquet_path = Path(args.parquet)
    else:
        candidates = sorted(DATA_DIR.glob("recommendations_*.parquet"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("[오류] recommendations parquet 없음. 먼저 run_pipeline.py 실행하세요.")
            sys.exit(1)
        parquet_path = candidates[0]

    print("=" * 60)
    print("Genre Precision@k 평가")
    print(f"  parquet: {parquet_path.name}")
    print(f"  sample:  {args.sample:,}건")
    print("=" * 60)

    print("[2/3] 추천 결과 로드 중...")
    rec_df = pd.read_parquet(parquet_path)
    print(f"  → {len(rec_df):,}건 로드 완료")

    conn = get_connection()
    try:
        meta_df = load_vod_meta(conn)
    finally:
        conn.close()

    print("[3/3] Precision@k 계산 중...")
    results = {}
    for field, label in [("genre", "장르"), ("ct_cl", "콘텐츠유형")]:
        for k in [5, 10, 20]:
            key = f"{label} Precision@{k}"
            results[key] = calc_precision_at_k(rec_df, meta_df, field, k, args.sample)

    print()
    print("=" * 60)
    print("평가 결과")
    print("=" * 60)
    for key, val in results.items():
        print(f"  {key:<25} {val:.4f}  ({val*100:.1f}%)")
    print("=" * 60)
    print(f"(샘플 {args.sample:,}건 기준)")


if __name__ == "__main__":
    main()
