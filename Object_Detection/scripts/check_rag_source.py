"""rag_source 값 분포 + genre_detail 분포 조회"""
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

print("=== rag_source 분포 ===")
cur.execute("SELECT rag_source, COUNT(*) FROM vod GROUP BY rag_source ORDER BY COUNT(*) DESC")
for src, cnt in cur.fetchall():
    print(f"  {src}: {cnt}건")

print("\n=== genre_detail 중 여행/음식 ===")
cur.execute("""
    SELECT genre_detail, COUNT(*)
    FROM vod
    WHERE genre_detail IN ('여행', '음식_먹방')
    GROUP BY genre_detail
""")
for genre, cnt in cur.fetchall():
    print(f"  {genre}: {cnt}건")

print("\n=== 여행/음식_먹방의 rag_source 분포 ===")
cur.execute("""
    SELECT rag_source, COUNT(*)
    FROM vod
    WHERE genre_detail IN ('여행', '음식_먹방')
    GROUP BY rag_source
    ORDER BY COUNT(*) DESC
""")
for src, cnt in cur.fetchall():
    print(f"  {src}: {cnt}건")

conn.close()
