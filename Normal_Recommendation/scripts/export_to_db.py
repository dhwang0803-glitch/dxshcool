"""
추천 결과 DB 적재 스크립트 (조장 전용)

사용법:
  python scripts/export_to_db.py --from-parquet data/recommendations_popular_20260317.parquet
  python scripts/export_to_db.py --from-parquet data/recommendations_popular_20260317.parquet --dry-run
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.db import get_conn

RECOMMENDATION_TYPE = "POPULAR"
TTL_DAYS = 7  # 1주일 1회 업데이트

DELETE_SQL = """
    DELETE FROM serving.popular_recommendation
"""

INSERT_SQL = """
    INSERT INTO serving.popular_recommendation
        (ct_cl, rank, vod_id_fk, score, recommendation_type, expires_at)
    VALUES (%s, %s, %s, %s, %s, %s)
"""


def export(df: pd.DataFrame, conn=None, dry_run: bool = False) -> None:
    """
    parquet DataFrame을 serving.popular_recommendation에 적재.
    conn이 None이면 새 연결 생성.
    """
    expires_at = datetime.now() + timedelta(days=TTL_DAYS)

    rows = [
        (
            row["ct_cl"],
            int(row["rank"]),
            row["vod_id_fk"],
            float(row["score"]),
            RECOMMENDATION_TYPE,
            expires_at,
        )
        for _, row in df.iterrows()
    ]

    if dry_run:
        print(f"[DRY-RUN] DELETE FROM serving.popular_recommendation (전체)")
        print(f"[DRY-RUN] INSERT 예정: {len(rows):,}건")
        print(f"[DRY-RUN] expires_at: {expires_at}")
        print(df.head(10).to_string(index=False))
        return

    def _do_export(conn):
        with conn.cursor() as cur:
            cur.execute(DELETE_SQL)
            deleted = cur.rowcount
            print(f"[INFO] 기존 레코드 전체 삭제: {deleted:,}건")

            cur.executemany(INSERT_SQL, rows)
            print(f"[INFO] 신규 INSERT: {len(rows):,}건")
            print(f"[INFO] expires_at: {expires_at}")

    if conn is not None:
        _do_export(conn)
    else:
        with get_conn() as new_conn:
            _do_export(new_conn)

    print("[INFO] DB 적재 완료.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="인기 추천 결과 DB 적재 (조장 전용)")
    parser.add_argument("--from-parquet", required=True, metavar="FILE", help="적재할 parquet 파일 경로")
    parser.add_argument("--dry-run", action="store_true", help="실제 DB 저장 없이 예정 건수만 출력")
    args = parser.parse_args()

    if not os.path.exists(args.from_parquet):
        print(f"[ERROR] 파일 없음: {args.from_parquet}")
        sys.exit(1)

    df = pd.read_parquet(args.from_parquet)
    print(f"[INFO] parquet 로드: {len(df):,}건 ({args.from_parquet})")

    export(df, conn=None, dry_run=args.dry_run)
