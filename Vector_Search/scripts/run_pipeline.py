"""
Vector Search 전체 파이프라인 자동 실행 (배치 행렬 연산)

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

    # 배치 크기 조정 (메모리 부족 시 줄이기)
    python scripts/run_pipeline.py --batch-size 500
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

    clip_ids = clip_df["vod_id_fk"].values

    return meta_df, meta_vecs, clip_df, clip_vecs, clip_ids


def process_batch(
    batch_indices,
    meta_ids, meta_vecs,
    clip_ids, clip_vecs,
    clip_id2meta_idx,
    alpha, top_n,
    valid_clip_idx, valid_meta_idx,
):
    """
    배치 단위 행렬 연산:
    batch_vecs (B, D) @ meta_vecs.T (D, N) → (B, N) 유사도 행렬 한 번에 계산
    """
    B = len(batch_indices)

    # PLAN_01: content_score 배치 행렬 곱 (B, N)
    batch_meta_vecs = meta_vecs[batch_indices]          # (B, 384)
    content_sim = batch_meta_vecs @ meta_vecs.T         # (B, N)

    # PLAN_02: clip_score 배치 행렬 곱 (B, M)
    # 배치 VOD 중 clip 임베딩 있는 것만 추출
    batch_vod_ids = meta_ids[batch_indices]
    clip_sim = np.zeros((B, len(clip_ids)), dtype=np.float32)
    for b_i, vod_id in enumerate(batch_vod_ids):
        if vod_id in clip_id2meta_idx:
            c_idx = clip_id2meta_idx[vod_id]
            clip_sim[b_i] = clip_vecs @ clip_vecs[c_idx]   # (M,)

    all_rows = []
    for b_i, vod_id in enumerate(batch_vod_ids):
        src_meta_idx = batch_indices[b_i]

        # clip_score를 meta 인덱스 기준으로 정렬 (numpy 인덱싱으로 한 번에 처리)
        clip_score_by_meta = np.zeros(len(meta_ids), dtype=np.float32)
        clip_score_by_meta[valid_meta_idx] = clip_sim[b_i, valid_clip_idx]

        # PLAN_03: 앙상블
        has_clip = clip_score_by_meta > 0.0
        eff_alpha = np.where(has_clip, alpha, 0.0)
        final_scores = eff_alpha * clip_score_by_meta + (1 - eff_alpha) * content_sim[b_i]

        # 자기 자신 제외
        final_scores[src_meta_idx] = -1.0

        # TOP-N 추출
        top_idx = np.argpartition(final_scores, -top_n)[-top_n:]
        top_idx = top_idx[np.argsort(final_scores[top_idx])[::-1]]

        for rank, idx in enumerate(top_idx, 1):
            all_rows.append({
                "source_vod_id": vod_id,
                "vod_id_fk": meta_ids[idx],
                "rank": rank,
                "score": round(float(final_scores[idx]), 6),
                "clip_score": round(float(clip_score_by_meta[idx]), 6),
                "content_score": round(float(content_sim[b_i, idx]), 6),
                "recommendation_type": "CONTENT_BASED",
            })

    return all_rows


def main():
    parser = argparse.ArgumentParser(description="Vector Search 전체 파이프라인 (배치 행렬 연산)")
    parser.add_argument("--vod-id", default=None, help="특정 VOD만 처리")
    parser.add_argument("--limit", type=int, default=None, help="처리할 VOD 수 제한")
    parser.add_argument("--alpha", type=float, default=None, help="CLIP 가중치 override")
    parser.add_argument("--out-file", default=None, help="출력 parquet 경로")
    parser.add_argument("--batch-size", type=int, default=1000, help="배치 크기 (기본 1000)")
    args = parser.parse_args()

    config = load_config()
    alpha = args.alpha if args.alpha is not None else config["ensemble"]["alpha"]
    top_n = config["ensemble"]["top_n"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = args.out_file or str(DATA_DIR / f"recommendations_{timestamp}.parquet")
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Vector Search 파이프라인 시작 (배치 행렬 연산)")
    print(f"  alpha={alpha}, top_n={top_n}, batch_size={args.batch_size}")
    print(f"  출력: {out_file}")
    print("=" * 60)

    # 벡터 로드
    meta_df, meta_vecs, clip_df, clip_vecs, clip_ids = load_embeddings()
    meta_ids = meta_df["vod_id_fk"].values

    # clip vod_id → clip 인덱스 매핑
    clip_id2meta_idx = {vid: i for i, vid in enumerate(clip_ids)}

    # clip_to_meta 사전 계산 (배치마다 재계산 방지)
    meta_id2idx = {vid: i for i, vid in enumerate(meta_ids)}
    clip_to_meta = np.array([meta_id2idx.get(cid, -1) for cid in clip_ids], dtype=np.int32)
    valid_mask = clip_to_meta >= 0
    valid_clip_idx = np.where(valid_mask)[0]
    valid_meta_idx = clip_to_meta[valid_mask]

    # 대상 VOD 인덱스
    if args.vod_id:
        indices = np.where(meta_ids == args.vod_id)[0]
    else:
        indices = np.arange(len(meta_ids))
        if args.limit:
            indices = indices[: args.limit]

    total = len(indices)
    print(f"\n[PLAN_01~03] 유사도 계산 시작 — 대상 {total:,}건")

    all_rows = []
    for start in range(0, total, args.batch_size):
        batch_indices = indices[start: start + args.batch_size]
        rows = process_batch(
            batch_indices, meta_ids, meta_vecs,
            clip_ids, clip_vecs, clip_id2meta_idx,
            alpha, top_n,
            valid_clip_idx, valid_meta_idx,
        )
        all_rows.extend(rows)
        done = min(start + args.batch_size, total)
        print(f"  [{done}/{total}] 누적 {len(all_rows):,}건")

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
