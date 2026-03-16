"""
VPC DB에서 임베딩 벡터를 로컬 parquet으로 1회 다운로드

사용법:
    python Vector_Search/scripts/dump_embeddings.py

출력:
    Vector_Search/data/meta_embeddings.parquet   ← vod_meta_embedding (384차원)
    Vector_Search/data/clip_embeddings.parquet   ← vod_embedding CLIP (512차원)

※ 이 스크립트는 최초 1회만 실행. 이후 run_pipeline.py는 로컬 parquet 사용.
"""
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection

DATA_DIR = Path(__file__).parent.parent / "data"
META_PARQUET = DATA_DIR / "meta_embeddings.parquet"
CLIP_PARQUET = DATA_DIR / "clip_embeddings.parquet"


def dump_meta_embeddings(conn):
    print("[1/2] vod_meta_embedding 다운로드 중...")
    cur = conn.cursor()
    cur.execute("SELECT vod_id_fk, embedding FROM vod_meta_embedding ORDER BY vod_id_fk")
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["vod_id_fk", "embedding"])
    df["embedding"] = df["embedding"].apply(list)
    df.to_parquet(META_PARQUET, index=False)
    print(f"  → {len(df):,}건 저장: {META_PARQUET}")
    return len(df)


def dump_clip_embeddings(conn):
    print("[2/2] vod_embedding (CLIP) 다운로드 중...")
    cur = conn.cursor()
    cur.execute(
        "SELECT vod_id_fk, embedding FROM vod_embedding WHERE model_name = 'clip-ViT-B-32' ORDER BY vod_id_fk"
    )
    rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=["vod_id_fk", "embedding"])
    df["embedding"] = df["embedding"].apply(list)
    df.to_parquet(CLIP_PARQUET, index=False)
    print(f"  → {len(df):,}건 저장: {CLIP_PARQUET}")
    return len(df)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("임베딩 벡터 로컬 dump 시작")
    print("=" * 60)

    conn = get_connection()
    try:
        meta_cnt = dump_meta_embeddings(conn)
        clip_cnt = dump_clip_embeddings(conn)
    finally:
        conn.close()

    print("=" * 60)
    print(f"완료: meta {meta_cnt:,}건 / clip {clip_cnt:,}건")
    print(f"저장 위치: {DATA_DIR}")
    print("이제 run_pipeline.py 실행 가능합니다.")
    print("=" * 60)


if __name__ == "__main__":
    main()
