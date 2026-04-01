"""19건 VOD의 DB smry(줄거리) 조회"""
import os, json
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

METADATA_PATH = Path(__file__).parent.parent.parent / "Object_Detection" / "data" / "batch_target" / "vod_metadata.json"

with open(METADATA_PATH, encoding="utf-8") as f:
    metadata = json.load(f)

conn = psycopg2.connect(
    host=os.getenv("DB_HOST"), port=int(os.getenv("DB_PORT", "5432")),
    dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
)
cur = conn.cursor()

for item in metadata:
    asset_nm = item["asset_nm"]
    cur.execute("""
        SELECT full_asset_id, asset_nm, smry, genre_detail
        FROM vod
        WHERE asset_nm ILIKE %s
        LIMIT 1
    """, (f"%{asset_nm}%",))
    row = cur.fetchone()
    if row:
        aid, name, smry, genre = row
        smry_short = (smry[:80] + "...") if smry and len(smry) > 80 else (smry or "NULL")
        print(f"\n  ✅ {item['file_id']}")
        print(f"    asset_nm: {name}")
        print(f"    smry: {smry_short}")
        print(f"    full_asset_id: {aid}")
    else:
        print(f"\n  ❌ {item['file_id']} ({asset_nm}) — DB에 없음")

conn.close()
