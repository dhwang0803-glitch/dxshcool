"""
유사 콘텐츠 검색 스크립트 (단건 조회)

사용법:
    python scripts/search.py --vod-id <full_asset_id>
    python scripts/search.py --vod-id <full_asset_id> --alpha 0.6
    python scripts/search.py --vod-id <full_asset_id> --top-n 10
"""
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection
from src.content_based import get_similar_by_meta
from src.clip_based import get_similar_by_clip
from src.ensemble import ensemble_scores, load_config


def main():
    parser = argparse.ArgumentParser(description="유사 VOD 검색")
    parser.add_argument("--vod-id", required=True, help="기준 VOD full_asset_id")
    parser.add_argument("--alpha", type=float, default=None, help="CLIP 가중치 override")
    parser.add_argument("--top-n", type=int, default=None, help="반환 건수 override")
    args = parser.parse_args()

    config = load_config()
    alpha = args.alpha if args.alpha is not None else config["ensemble"]["alpha"]
    top_n = args.top_n if args.top_n is not None else config["ensemble"]["top_n"]

    conn = get_connection()
    try:
        content_results = get_similar_by_meta(args.vod_id, conn, top_n=top_n * 2)
        clip_results = get_similar_by_clip(args.vod_id, conn, top_n=top_n * 2)
        results = ensemble_scores(clip_results, content_results, alpha=alpha, top_n=top_n)

        print(f"\n[유사 VOD TOP-{top_n}] 기준: {args.vod_id}  (alpha={alpha})")
        print("-" * 70)
        for i, r in enumerate(results, 1):
            print(
                f"{i:2d}. {r['vod_id']:<35}"
                f"  final={r['final_score']:.4f}"
                f"  clip={r['clip_score']:.4f}"
                f"  content={r['content_score']:.4f}"
            )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
