"""DB 전체 스키마 조회 — 탐지/광고 테이블 + vod 컬럼 확인"""
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
import psycopg2

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
cur = conn.cursor()

# 1. vod 테이블 컬럼
print("=" * 60)
print("  vod 테이블 컬럼")
print("=" * 60)
cur.execute("""
    SELECT column_name, data_type, is_nullable
    FROM information_schema.columns
    WHERE table_schema='public' AND table_name='vod'
    ORDER BY ordinal_position
""")
for name, dtype, null in cur.fetchall():
    print(f"  {name:<30} {dtype:<25} {'NULL' if null=='YES' else 'NOT NULL'}")

# 2. 탐지/광고 테이블 존재 + 컬럼
print(f"\n{'=' * 60}")
print("  탐지/광고 테이블")
print("=" * 60)
targets = [
    ('public', 'detected_object_yolo'),
    ('public', 'detected_object_clip'),
    ('public', 'detected_object_stt'),
    ('public', 'detected_object_ocr'),
    ('public', 'vod_ad_summary'),
    ('public', 'seasonal_market'),
    ('serving', 'shopping_ad'),
]
for schema, table in targets:
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema=%s AND table_name=%s
        ORDER BY ordinal_position
    """, (schema, table))
    cols = cur.fetchall()
    if cols:
        print(f"\n  ✅ {schema}.{table} ({len(cols)}개 컬럼)")
        for name, dtype, null in cols:
            print(f"    {name:<25} {dtype:<25} {'NULL' if null=='YES' else 'NOT NULL'}")
    else:
        print(f"\n  ❌ {schema}.{table} — 없음")

# 3. serving 스키마 존재 여부
cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name='serving'")
print(f"\n  serving 스키마: {'✅ 있음' if cur.fetchone() else '❌ 없음'}")

conn.close()
