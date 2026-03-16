"""
Vector Search 전체 파이프라인 자동 실행 (로컬 parquet 기반)

PLAN_01 (content_score) + PLAN_02 (clip_score) + PLAN_03 (앙상블) + PLAN_04 (parquet 저장)

사전 조건:
    python Vector_Search/scripts/dump_embeddings.py  ← 최초 1회 실행 필요

사용법:
    # 전체 VOD 실행
    python scripts/run_pipeline.py

    # 특정 VOD만
    python scripts/run_pipeline.py --vod-id <full_asset_id>

    # 테스트용 (100건만)
    python scripts/run_pipeline.py --limit 100

    # alpha override
    python scripts/run_pipeline.py --alpha 0.6
"""
import argparse
import sys
from pathlib import Path
from datetime import datetime

import numpy as np
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ensemble import load_config

DATA_DIR = Path(__file__).parent.parent / "data"
META_PARQUET = DATA_DIR / "meta_embeddings.parquet"
CLIP_PARQUET = DATA_DIR / "clip_embeddings.parquet"


def load_embeddings():
    """로컬 parquet에서 벡터 로드 후 numpy 정규화"""
    if not META_PARQUET.exists() or not CLIP_PARQUET.exists():
        print("[오류] 임베딩 parquet 파일 없음. 먼저 실행하세요:")
        print("  python Vector_Search/scripts/dump_embeddings.py")
        sys.exit(1)

    print("[로드] meta_embeddings.parquet ...", end=" ", flush=True)
    meta_df = pd.read_parquet(META_PARQUET)
    meta_vecs = np.array(meta_df["embedding"].tolist(), dtype=np.float32)
    meta_vecs /= np.linalg.norm(meta_vecs, axis=1, keepdims=True) + 1e-10
    print(f"{len(meta_df):,}건")

    print("[로드] clip_embeddings.parquet ...", end=" ", flush=True)
    clip_df = pd.read_parquet(CLIP_PARQUET)
    clip_vecs = np.array(clip_df["embedding"].tolist(), dtype=np.float32)
    clip_vecs /= np.linalg.norm(clip_vecs, axis=1, keepdims=True) + 1e-10
    print(f"{len(clip_df):,}건")

    # clip vod_id → 인덱스 매핑
    clip_id2idx = {vid: i for i, vid in enumerate(clip_df["vod_id_fk"])}

    return meta_df, meta_vecs, clip_df, clip_vecs, clip_id2idx


def compute_similar(vod_id, meta_df, meta_vecs, clip_vecs, clip_id2idx, alpha, top_n):
    """로컬 numpy로 content_score + clip_score 계산 후 앙상블"""
    meta_ids = meta_df["vod_id_fk"].values

    # PLAN_01: content_score (메타 코사인 유사도)
    meta_idx_arr = np.where(meta_ids == vod_id)[0]
    if len(meta_idx_arr) == 0:
        return []
    meta_idx = meta_idx_arr[0]
    content_scores = meta_vecs @ meta_vecs[meta_idx]  # (N,)

    # PLAN_02: clip_score (CLIP 코사인 유사도)
    clip_scores_map = {}
    if vod_id in clip_id2idx:
        clip_idx = clip_id2idx[vod_id]
        raw_clip = clip_vecs @ clip_vecs[clip_idx]  # (M,)
        clip_ids = list(clip_id2idx.keys())
        for j, cid in enumerate(clip_ids):
            clip_scores_map[cid] = float(raw_clip[j])

    # PLAN_03: 앙상블
    results = []
    for i, vid in enumerate(meta_ids):
        if vid == vod_id:
            continue
        cscore = float(content_scores[i])
        clscore = clip_scores_map.get(vid, 0.0)
        eff_alpha = alpha if clscore > 0.0 else 0.0
        final = eff_alpha * clscore + (1 - eff_alpha) * cscore
        results.append({
            "vod_id": vid,
            "final_score": round(final, 6),
            "clip_score": clscore,
            "content_score": cscore,
        })

    return sorted(results, key=lambda x: x["final_score"], reverse=True)[:top_n]


def main():
    parser = argparse.ArgumentParser(description="Vector Search 전체 파이프라인")
    parser.add_argument("--vod-id", default=None, help="특정 VOD만 처리")
    parser.add_argument("--limit", type=int, default=None, help="처리할 VOD 수 제한")
    parser.add_argument("--alpha", type=float, default=None, help="CLIP 가중치 override")
    parser.add_argument("--out-file", default=None, help="출력 parquet 경로")
    args = parser.parse_args()

    config = load_config()
    alpha = args.alpha if args.alpha is not None else config["ensemble"]["alpha"]
    top_n = config["ensemble"]["top_n"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = args.out_file or str(DATA_DIR / f"recommendations_{timestamp}.parquet")
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Vector Search 파이프라인 시작 (로컬 numpy 계산)")
    print(f"  alpha={alpha}, top_n={top_n}")
    print(f"  출력: {out_file}")
    print("=" * 60)

    # 벡터 로드
    meta_df, meta_vecs, clip_df, clip_vecs, clip_id2idx = load_embeddings()

    # 대상 VOD 목록
    if args.vod_id:
        vod_ids = [args.vod_id]
    else:
        vod_ids = list(meta_df["vod_id_fk"].values)
        if args.limit:
            vod_ids = vod_ids[: args.limit]

    total = len(vod_ids)
    print(f"\n[PLAN_01~03] 유사도 계산 시작 — 대상 {total:,}건")

    all_rows = []
    for i, vod_id in enumerate(vod_ids, 1):
        results = compute_similar(vod_id, meta_df, meta_vecs, clip_vecs, clip_id2idx, alpha, top_n)
        for rank, r in enumerate(results, 1):
            all_rows.append({
                "source_vod_id": vod_id,
                "vod_id_fk": r["vod_id"],
                "rank": rank,
                "score": r["final_score"],
                "clip_score": r["clip_score"],
                "content_score": r["content_score"],
                "recommendation_type": "CONTENT_BASED",
            })

        if i % 1000 == 0 or i == total:
            print(f"  [{i}/{total}] 누적 {len(all_rows):,}건")

    # PLAN_04: parquet 저장
    print(f"\n[PLAN_04] parquet 저장 중...")
    df = pd.DataFrame(all_rows)
    df.to_parquet(out_file, index=False)

    print("=" * 60)
    print(f"파이프라인 완료")
    print(f"  처리 VOD: {total:,}건")
    print(f"  추천 결과: {len(df):,}건")
    print(f"  출력 파일: {out_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
