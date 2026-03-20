"""
check_target_vods.py — 배치 처리 대상 VOD 조회

genre_detail IN ('여행', '음식_먹방') AND rag_source = 'tmdb_new_2025'

실행:
    cd Object_Detection
    python scripts/check_target_vods.py
"""
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # youtube_video_id 컬럼 존재 여부 확인
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'vod' AND column_name = 'youtube_video_id'
    """)
    has_yt_col = cur.fetchone() is not None

    # 장르별 건수
    if has_yt_col:
        cur.execute("""
            SELECT genre_detail, COUNT(*) as cnt,
                   COUNT(youtube_video_id) as has_yt
            FROM vod
            WHERE rag_source = 'tmdb_new_2025'
              AND genre_detail IN ('여행', '음식_먹방')
            GROUP BY genre_detail
            ORDER BY genre_detail
        """)
    else:
        cur.execute("""
            SELECT genre_detail, COUNT(*) as cnt, 0 as has_yt
            FROM vod
            WHERE rag_source = 'tmdb_new_2025'
              AND genre_detail IN ('여행', '음식_먹방')
            GROUP BY genre_detail
            ORDER BY genre_detail
        """)

    rows = cur.fetchall()

    print("=" * 50)
    print("  배치 처리 대상 VOD 조회")
    print("  조건: rag_source='tmdb_new_2025'")
    print("        genre_detail IN ('여행', '음식_먹방')")
    print("=" * 50)

    if not has_yt_col:
        print("  ⚠️ youtube_video_id 컬럼 미생성 (마이그레이션 필요)")

    total = 0
    for genre, cnt, has_yt in rows:
        total += cnt
        if has_yt_col:
            print(f"  {genre}: {cnt}건 (youtube_id: {has_yt}건)")
        else:
            print(f"  {genre}: {cnt}건")

    print(f"\n  합계: {total}건")

    # 샘플 5건
    cur.execute("""
        SELECT full_asset_id, asset_nm, genre_detail
        FROM vod
        WHERE rag_source = 'tmdb_new_2025'
          AND genre_detail IN ('여행', '음식_먹방')
        LIMIT 5
    """)
    samples = cur.fetchall()
    if samples:
        print(f"\n  샘플 5건:")
        for aid, name, genre in samples:
            print(f"    {genre} | {aid[:30]} | {name[:40]}")

    conn.close()


if __name__ == "__main__":
    main()
