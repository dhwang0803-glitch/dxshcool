"""배치 대상 4개 시리즈 DB 검색 — full_asset_id 매핑 확인"""
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

keywords = [
    ("동원아 여행가자", ["06", "11", "12", "15", "16"]),
    ("서울촌놈", ["01", "02", "03", "05", "07", "09"]),
    ("알토란", ["490", "418", "440", "496"]),
    ("로컬식탁", []),
]

for name, eps in keywords:
    cur.execute("""
        SELECT full_asset_id, asset_nm, genre_detail, youtube_video_id
        FROM vod
        WHERE asset_nm ILIKE %s OR series_nm ILIKE %s
        ORDER BY asset_nm
        LIMIT 30
    """, (f"%{name}%", f"%{name}%"))
    rows = cur.fetchall()
    print(f"\n{'=' * 60}")
    print(f"  '{name}' → {len(rows)}건")
    print(f"{'=' * 60}")
    if rows:
        for aid, aname, genre, ytid in rows[:15]:
            yt = f"https://youtube.com/watch?v={ytid}" if ytid else "없음"
            print(f"  {genre or '-'} | {aname[:40]} | {aid[:30]} | yt={yt[:50]}")
        if len(rows) > 15:
            print(f"  ... +{len(rows)-15}건")
    else:
        print(f"  결과 없음")

conn.close()
