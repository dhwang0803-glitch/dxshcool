"""cluster_assignments.parquet → public.user_segment 적재.

Usage:
    python gen_rec_sentence/scripts/ingest_user_segments.py
    python gen_rec_sentence/scripts/ingest_user_segments.py --dry-run
"""

import argparse
import logging
import sys
import os

import pandas as pd
import psycopg2
import psycopg2.extras

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(".env")

from gen_rec_sentence.src.context_builder import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_ASSIGNMENTS_PATH = "gen_rec_sentence/data/cluster_assignments.parquet"
_BATCH_SIZE = 5_000


def ingest(conn, df: pd.DataFrame, dry_run: bool) -> None:
    total = len(df)
    log.info("적재 대상: %d명", total)

    if dry_run:
        log.info("[DRY-RUN] 실제 적재 없이 종료")
        return

    upserted = 0
    rows = [
        (str(row["user_id"]), int(row["cluster_id"]))
        for _, row in df.iterrows()
    ]

    with conn.cursor() as cur:
        for i in range(0, len(rows), _BATCH_SIZE):
            batch = rows[i: i + _BATCH_SIZE]
            psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO public.user_segment (user_id_fk, segment_id)
                VALUES %s
                ON CONFLICT (user_id_fk) DO UPDATE
                    SET segment_id  = EXCLUDED.segment_id,
                        assigned_at = NOW()
                """,
                batch,
            )
            upserted += len(batch)
            log.info("  %d / %d 처리 완료", upserted, total)

    conn.commit()
    log.info("user_segment 적재 완료: %d행 UPSERT", upserted)

    # 적재 결과 확인
    with conn.cursor() as cur:
        cur.execute(
            "SELECT segment_id, COUNT(*) FROM public.user_segment GROUP BY segment_id ORDER BY segment_id"
        )
        for seg_id, cnt in cur.fetchall():
            log.info("  segment %d: %d명", seg_id, cnt)


def main() -> None:
    parser = argparse.ArgumentParser(description="user_segment DB 적재")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    df = pd.read_parquet(_ASSIGNMENTS_PATH)
    log.info("parquet 로드: %s (shape=%s)", _ASSIGNMENTS_PATH, df.shape)

    conn = get_conn()
    try:
        ingest(conn, df, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
