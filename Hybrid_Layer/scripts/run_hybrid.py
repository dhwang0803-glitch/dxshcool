"""Phase 3 실행: CF + Vector 후보 리랭킹 → hybrid_recommendation 적재.

Usage:
    python Hybrid_Layer/scripts/run_hybrid.py
    python Hybrid_Layer/scripts/run_hybrid.py --beta 0.7 --top-n 10
"""

import argparse
import logging
import sys

import yaml

sys.path.insert(0, ".")

from Hybrid_Layer.src.db import get_conn
from Hybrid_Layer.src.reranker import run_hybrid_reranking

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    # config 로드
    with open("Hybrid_Layer/config/hybrid_config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    rr = config.get("reranking", {})
    batch = config.get("batch", {})

    parser = argparse.ArgumentParser(description="Phase 3: Hybrid 리랭킹")
    parser.add_argument("--beta", type=float, default=rr.get("beta", 0.6))
    parser.add_argument("--top-n", type=int, default=rr.get("top_n", 10))
    parser.add_argument("--top-k-tags", type=int, default=rr.get("top_k_tags", 3))
    parser.add_argument("--chunk-size", type=int, default=batch.get("user_chunk_size", 1000))
    args = parser.parse_args()

    conn = get_conn()
    try:
        total = run_hybrid_reranking(
            conn,
            beta=args.beta,
            top_n=args.top_n,
            top_k_tags=args.top_k_tags,
            user_chunk_size=args.chunk_size,
        )
        log.info("Phase 3 완료: %d rows inserted", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
