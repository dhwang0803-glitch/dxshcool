"""
Vector Search 전체 파이프라인 자동 실행

PLAN_01 (content_score) + PLAN_02 (clip_score) + PLAN_03 (앙상블) + PLAN_04 (parquet 저장)

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
import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection
from src.content_based import get_similar_by_meta
from src.clip_based import get_similar_by_clip
from src.ensemble import ensemble_scores, load_config


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
    out_file = args.out_file or f"data/recommendations_{timestamp}.parquet"
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Vector Search 파이프라인 시작")
    print(f"  alpha={alpha}, top_n={top_n}")
    print(f"  출력: {out_file}")
    print("=" * 60)

    conn = get_connection()
    try:
        # 대상 VOD 목록 조회
        if args.vod_id:
            vod_ids = [args.vod_id]
        else:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT vod_id_fk FROM vod_meta_embedding ORDER BY vod_id_fk"
            )
            vod_ids = [r[0] for r in cur.fetchall()]
            if args.limit:
                vod_ids = vod_ids[: args.limit]

        total = len(vod_ids)
        print(f"\n[PLAN_01~03] 유사도 계산 시작 — 대상 {total:,}건")

        all_rows = []
        for i, vod_id in enumerate(vod_ids, 1):
            # PLAN_01: 메타데이터 기반 유사도
            content_results = get_similar_by_meta(vod_id, conn, top_n=top_n * 2)

            # PLAN_02: CLIP 영상 기반 유사도
            clip_results = get_similar_by_clip(vod_id, conn, top_n=top_n * 2)

            # PLAN_03: 앙상블
            results = ensemble_scores(clip_results, content_results, alpha=alpha, top_n=top_n)

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

            if i % 500 == 0 or i == total:
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

    finally:
        conn.close()


if __name__ == "__main__":
    main()
