"""
search_series.py — 조장님 지정 시리즈 DB 검색

대상: 동원아 여행가자, 서울촌놈, 알토란, 로컬식탁

실행:
    cd Object_Detection
    python scripts/search_series.py
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

    keywords = ["동원아 여행가자", "서울촌놈", "알토란", "로컬식탁"]

    for kw in keywords:
        cur.execute("""
            SELECT full_asset_id, asset_nm, genre_detail, series_nm, rag_source
            FROM vod
            WHERE asset_nm ILIKE %s OR series_nm ILIKE %s
            ORDER BY asset_nm
        """, (f"%{kw}%", f"%{kw}%"))
        rows = cur.fetchall()

        print(f"\n{'=' * 60}")
        print(f"  '{kw}' 검색 결과: {len(rows)}건")
        print(f"{'=' * 60}")

        if rows:
            # 장르/rag_source 분포
            genres = {}
            sources = {}
            for _, _, genre, _, src in rows:
                genres[genre] = genres.get(genre, 0) + 1
                sources[src] = sources.get(src, 0) + 1
            print(f"  장르: {genres}")
            print(f"  rag_source: {sources}")
            print(f"\n  처음 5건:")
            for aid, name, genre, series, src in rows[:5]:
                print(f"    {genre} | {name[:40]} | {src}")
            if len(rows) > 5:
                print(f"  ... +{len(rows)-5}건")
                print(f"\n  마지막 5건:")
                for aid, name, genre, series, src in rows[-5:]:
                    print(f"    {genre} | {name[:40]} | {src}")
        else:
            print(f"  결과 없음")

    conn.close()


if __name__ == "__main__":
    main()
