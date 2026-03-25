"""parquet 컬럼 vs DB 스키마 비교"""
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pandas as pd
import psycopg2

PARQUET_DIR = Path(__file__).parent.parent / "data" / "parquet_output"

def get_db_columns(cur, schema, table):
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
    """, (schema, table))
    return {row[0]: row[1] for row in cur.fetchall()}

def check_parquet(path, db_cols, table_name):
    if not path.exists():
        print(f"\n  ❌ {path.name} — 파일 없음")
        return

    df = pd.read_parquet(str(path))
    pq_cols = list(df.columns)
    pq_dtypes = {col: str(df[col].dtype) for col in df.columns}

    print(f"\n  {'=' * 60}")
    print(f"  {path.name} vs {table_name}")
    print(f"  parquet: {len(df)}행, {len(pq_cols)}컬럼")
    print(f"  {'=' * 60}")

    if not db_cols:
        print(f"  ⚠️ DB 테이블 없음 — parquet 컬럼만 표시")
        for col in pq_cols:
            print(f"    {col:<25} {pq_dtypes[col]:<15}")
        print(f"\n  샘플 3행:")
        print(df.head(3).to_string(index=False))
        return

    # 매핑 (parquet vod_id → DB vod_id_fk)
    col_map = {"vod_id": "vod_id_fk"}

    all_ok = True
    for pq_col in pq_cols:
        db_col = col_map.get(pq_col, pq_col)
        if db_col in db_cols:
            print(f"    ✅ {pq_col:<25} → {db_col:<25} ({pq_dtypes[pq_col]} → {db_cols[db_col]})")
        else:
            # auto-generated 컬럼 (id, created_at) 은 parquet에 없어도 됨
            print(f"    ⚠️ {pq_col:<25} → DB에 없음")
            all_ok = False

    # DB에 있는데 parquet에 없는 컬럼
    skip_cols = {"created_at", "detected_yolo_id", "detected_clip_id", "detected_stt_id", "detected_ocr_id"}
    for db_col, db_type in db_cols.items():
        if db_col in skip_cols:
            continue
        pq_match = db_col if db_col in pq_cols else ("vod_id" if db_col == "vod_id_fk" else None)
        if not pq_match and db_col not in [col_map.get(c, c) for c in pq_cols]:
            print(f"    ❌ DB {db_col:<25} ← parquet에 없음")
            all_ok = False

    if all_ok:
        print(f"\n  ✅ 매핑 OK")
    else:
        print(f"\n  ⚠️ 매핑 불일치 있음")

    print(f"\n  샘플 3행:")
    print(df.head(3).to_string(index=False))


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    checks = [
        ("vod_detected_object.parquet", "public", "detected_object_yolo"),
        ("vod_clip_concept.parquet", "public", "detected_object_clip"),
        ("vod_stt_concept.parquet", "public", "detected_object_stt"),
        ("vod_ocr_concept.parquet", "public", "detected_object_ocr"),
    ]

    for pq_name, schema, table in checks:
        db_cols = get_db_columns(cur, schema, table)
        check_parquet(PARQUET_DIR / pq_name, db_cols, f"{schema}.{table}")

    conn.close()


if __name__ == "__main__":
    main()
