"""Colab 배치 결과 parquet → DB UPSERT.

Colab에서 오프라인으로 생성한 results.parquet을 로컬에서 DB에 적재한다.

Usage:
    python gen_rec_sentence/scripts/ingest_results.py gen_rec_sentence/data/colab_data/results.parquet
    python gen_rec_sentence/scripts/ingest_results.py results.parquet --dry-run
"""

import argparse
import logging
import sys

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

_BATCH_SIZE = 500


def main():
    parser = argparse.ArgumentParser(description="Colab 결과 parquet → DB UPSERT")
    parser.add_argument("parquet_path", help="results.parquet 경로")
    parser.add_argument("--dry-run", action="store_true", help="DB 쓰기 없이 통계만 확인")
    args = parser.parse_args()

    df = pd.read_parquet(args.parquet_path)
    log.info("결과 로드: %d건 (%s)", len(df), args.parquet_path)

    # 필수 컬럼 확인
    required = {"vod_id", "segment_id", "rec_sentence", "model_name"}
    missing = required - set(df.columns)
    if missing:
        log.error("필수 컬럼 누락: %s", missing)
        sys.exit(1)

    # 통계
    log.info("세그먼트별 건수:")
    for seg_id, cnt in df.groupby("segment_id").size().items():
        log.info("  segment %d: %d건", seg_id, cnt)
    log.info("평균 문장 길이: %.1f자", df["rec_sentence"].str.len().mean())

    if args.dry_run:
        log.info("DRY-RUN 완료. DB 쓰기 없음.")
        return

    conn = get_conn()
    try:
        total = 0
        rows = df.to_dict("records")

        for start in range(0, len(rows), _BATCH_SIZE):
            batch = rows[start:start + _BATCH_SIZE]
            with conn.cursor() as cur:
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO serving.rec_sentence (vod_id_fk, segment_id, rec_sentence, model_name)
                    VALUES %s
                    ON CONFLICT (vod_id_fk, segment_id) DO UPDATE SET
                        rec_sentence = EXCLUDED.rec_sentence,
                        model_name   = EXCLUDED.model_name,
                        generated_at = NOW()
                    """,
                    [(r["vod_id"], int(r["segment_id"]), r["rec_sentence"], r["model_name"])
                     for r in batch],
                )
            conn.commit()
            total += len(batch)
            log.info("  UPSERT: %d / %d", total, len(rows))

        log.info("완료 — %d건 UPSERT", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
