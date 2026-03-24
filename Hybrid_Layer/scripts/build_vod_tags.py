"""Phase 1 실행: VOD 메타데이터 → vod_tag 태그 추출 + 적재.

Usage:
    python Hybrid_Layer/scripts/build_vod_tags.py
    python Hybrid_Layer/scripts/build_vod_tags.py --dry-run
"""

import argparse
import logging
import sys

sys.path.insert(0, ".")

from Hybrid_Layer.src.db import get_conn
from Hybrid_Layer.src.tag_builder import build_vod_tags, extract_tags_from_row

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Phase 1: VOD → vod_tag 태그 추출")
    parser.add_argument("--dry-run", action="store_true", help="DB 적재 없이 태그 수만 출력")
    args = parser.parse_args()

    conn = get_conn()
    try:
        if args.dry_run:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT full_asset_id, director, cast_lead, cast_guest,
                           genre, genre_detail, rating
                    FROM public.vod
                    WHERE full_asset_id IS NOT NULL
                    """
                )
                columns = [desc[0] for desc in cur.description]
                rows = [dict(zip(columns, r)) for r in cur.fetchall()]

            total = 0
            category_counts = {}
            for row in rows:
                tags = extract_tags_from_row(row)
                total += len(tags)
                for _, cat, _, _ in tags:
                    category_counts[cat] = category_counts.get(cat, 0) + 1

            log.info("[DRY-RUN] VOD: %d, 총 태그: %d", len(rows), total)
            for cat, cnt in sorted(category_counts.items()):
                log.info("  %s: %d", cat, cnt)
        else:
            inserted = build_vod_tags(conn)
            log.info("Phase 1 완료: %d tags inserted", inserted)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
