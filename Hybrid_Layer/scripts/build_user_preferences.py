"""Phase 2 실행: watch_history × vod_tag → user_preference 집계.

Usage:
    python Hybrid_Layer/scripts/build_user_preferences.py
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from Hybrid_Layer.src.db import get_conn
from Hybrid_Layer.src.preference_builder import build_user_preferences

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Phase 2: user_preference 집계")
    parser.add_argument(
        "--min-watch-count", type=int, default=2,
        help="최소 시청 횟수 (기본 2, DDL CHECK 제약)",
    )
    args = parser.parse_args()

    conn = get_conn()
    try:
        inserted = build_user_preferences(conn, min_watch_count=args.min_watch_count)
        log.info("Phase 2 완료: %d user_preference rows", inserted)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
