"""Phase 4 실행: 선호 태그별 VOD 추천 선반 → tag_recommendation 적재.

Usage:
    python Hybrid_Layer/scripts/build_tag_shelves.py
    python Hybrid_Layer/scripts/build_tag_shelves.py --vods-per-tag 10
"""

import argparse
import logging
import sys

import yaml

sys.path.insert(0, ".")

from Hybrid_Layer.src.db import get_conn
from Hybrid_Layer.src.shelf_builder import build_tag_shelves

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    with open("Hybrid_Layer/config/hybrid_config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tr = config.get("tag_recommendation", {})
    batch = config.get("batch", {})

    parser = argparse.ArgumentParser(description="Phase 4: 태그 선반 생성")
    parser.add_argument("--vods-per-tag", type=int, default=tr.get("vods_per_tag", 10))
    parser.add_argument("--chunk-size", type=int, default=batch.get("user_chunk_size", 1000))
    parser.add_argument(
        "--test-mode", action="store_true",
        help="테스터 격리 모드: is_test=TRUE 유저만 처리 → tag_recommendation_test 적재",
    )
    args = parser.parse_args()

    conn = get_conn()
    try:
        total = build_tag_shelves(
            conn,
            vods_per_tag=args.vods_per_tag,
            user_chunk_size=args.chunk_size,
            test_mode=args.test_mode,
        )
        log.info("Phase 4 완료: %d rows inserted", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
