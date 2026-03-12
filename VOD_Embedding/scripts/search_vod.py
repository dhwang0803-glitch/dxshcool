"""VOD 테이블 검색 유틸리티"""
import os
from pathlib import Path

# .env 로드
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    with open(env_path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                k, v = line.split('=', 1)
                os.environ[k.strip()] = v.strip()

import psycopg2

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT', '5432'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)

keyword = input("검색어: ")
cur = conn.cursor()
cur.execute(
    "SELECT full_asset_id, asset_nm, ct_cl, series_nm FROM vod WHERE asset_nm LIKE %s LIMIT 30",
    (f'%{keyword}%',)
)
rows = cur.fetchall()
print(f"\n결과: {len(rows)}건")
for r in rows:
    print(r)

conn.close()
