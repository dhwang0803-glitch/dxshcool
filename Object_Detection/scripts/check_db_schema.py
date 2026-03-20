"""
check_db_schema.py — vod 테이블 컬럼 + 대상 VOD 조회

실행:
    cd Object_Detection
    python scripts/check_db_schema.py
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

    # 1. vod 테이블 전체 컬럼 조회
    cur.execute("""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'vod'
        ORDER BY ordinal_position
    """)
    cols = cur.fetchall()
    print("=" * 60)
    print("  vod 테이블 컬럼 목록")
    print("=" * 60)
    for name, dtype, nullable in cols:
        print(f"  {name:<30} {dtype:<20} {'NULL' if nullable == 'YES' else 'NOT NULL'}")
    print(f"\n  총 {len(cols)}개 컬럼")

    # 2. youtube/trailer 관련 컬럼 존재 여부
    col_names = {c[0] for c in cols}
    print(f"\n  youtube_video_id: {'✅ 있음' if 'youtube_video_id' in col_names else '❌ 없음'}")
    print(f"  duration_sec:     {'✅ 있음' if 'duration_sec' in col_names else '❌ 없음'}")
    print(f"  trailer_processed:{'✅ 있음' if 'trailer_processed' in col_names else '❌ 없음'}")

    # 3. detection 테이블 존재 여부
    cur.execute("""
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_name IN (
            'detected_object_yolo', 'detected_object_clip',
            'detected_object_stt', 'detected_object_ocr',
            'vod_ad_summary', 'shopping_ad', 'seasonal_market'
        )
        ORDER BY table_schema, table_name
    """)
    tables = cur.fetchall()
    print(f"\n{'=' * 60}")
    print("  탐지/광고 관련 테이블 존재 여부")
    print("=" * 60)
    found = {t[1] for t in tables}
    for tbl in ['detected_object_yolo', 'detected_object_clip', 'detected_object_stt',
                'detected_object_ocr', 'vod_ad_summary', 'seasonal_market', 'shopping_ad']:
        schema = next((t[0] for t in tables if t[1] == tbl), '-')
        status = '✅' if tbl in found else '❌'
        print(f"  {status} {schema}.{tbl}")

    # 4. 대상 VOD 건수
    print(f"\n{'=' * 60}")
    print("  배치 대상 VOD (rag_source='tmdb_new_2025')")
    print("=" * 60)
    cur.execute("""
        SELECT genre_detail, COUNT(*) as cnt
        FROM vod
        WHERE rag_source = 'tmdb_new_2025'
          AND genre_detail IN ('여행', '음식_먹방')
        GROUP BY genre_detail
        ORDER BY genre_detail
    """)
    rows = cur.fetchall()
    total = 0
    for genre, cnt in rows:
        total += cnt
        print(f"  {genre}: {cnt}건")
    print(f"  합계: {total}건")

    # 5. youtube_video_id가 있으면 다운로드 가능 건수
    if 'youtube_video_id' in col_names:
        cur.execute("""
            SELECT COUNT(*)
            FROM vod
            WHERE rag_source = 'tmdb_new_2025'
              AND genre_detail IN ('여행', '음식_먹방')
              AND youtube_video_id IS NOT NULL
        """)
        yt_cnt = cur.fetchone()[0]
        print(f"  youtube_video_id 있는 것: {yt_cnt}건")

        cur.execute("""
            SELECT full_asset_id, asset_nm, genre_detail, youtube_video_id
            FROM vod
            WHERE rag_source = 'tmdb_new_2025'
              AND genre_detail IN ('여행', '음식_먹방')
              AND youtube_video_id IS NOT NULL
            LIMIT 5
        """)
        samples = cur.fetchall()
        if samples:
            print(f"\n  샘플 5건:")
            for aid, name, genre, ytid in samples:
                url = f"https://youtube.com/watch?v={ytid}"
                print(f"    {genre} | {name[:30]} | {url}")

    conn.close()


if __name__ == "__main__":
    main()
