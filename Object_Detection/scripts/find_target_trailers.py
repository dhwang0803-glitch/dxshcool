"""
find_target_trailers.py — 대상 VOD 29건의 트레일러 보유 현황 확인

1. DB에서 TMDB_NEW_2025 + 여행/음식_먹방 VOD 목록 조회
2. 로컬 트레일러 디렉토리에서 매칭 확인
3. 매칭된 트레일러 목록 출력

실행:
    cd Object_Detection
    python scripts/find_target_trailers.py
"""
import os
import sys
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent
TRAILERS_DIR = PROJECT_ROOT.parent / "VOD_Embedding" / "data" / "trailers_아름"


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # 대상 VOD 조회
    cur.execute("""
        SELECT full_asset_id, asset_nm, genre_detail
        FROM vod
        WHERE rag_source = 'TMDB_NEW_2025'
          AND genre_detail IN ('여행', '음식_먹방')
        ORDER BY genre_detail, asset_nm
    """)
    vods = cur.fetchall()
    conn.close()

    print(f"=" * 60)
    print(f"  대상 VOD: {len(vods)}건")
    print(f"  트레일러 디렉토리: {TRAILERS_DIR}")
    print(f"=" * 60)

    # 로컬 트레일러 파일 목록
    if TRAILERS_DIR.exists():
        local_files = {f.stem: f for f in TRAILERS_DIR.glob("*.mp4")}
        # full_asset_id의 | → # 변환 (파일명에서)
        local_stems = set()
        for stem in local_files:
            # 파일명: cjc#M0130664LSGJ24872601__20kaO225J20.mp4
            asset_part = stem.split("__")[0].replace("#", "|")
            local_stems.add(asset_part)
    else:
        local_files = {}
        local_stems = set()
        print(f"\n  ⚠️ 트레일러 디렉토리 없음: {TRAILERS_DIR}")

    print(f"  로컬 트레일러 총: {len(local_files)}개")

    # 매칭 확인
    matched = []
    unmatched = []
    for aid, name, genre in vods:
        if aid in local_stems:
            # 매칭된 파일 찾기
            file_key = aid.replace("|", "#")
            trailer = next((f for s, f in local_files.items() if s.startswith(file_key)), None)
            matched.append((aid, name, genre, trailer))
        else:
            unmatched.append((aid, name, genre))

    print(f"\n  트레일러 있음: {len(matched)}건")
    print(f"  트레일러 없음: {len(unmatched)}건")

    if matched:
        print(f"\n  === 트레일러 있는 VOD ===")
        for aid, name, genre, trailer in matched:
            print(f"    {genre} | {name[:35]} | {trailer.name if trailer else '?'}")

    if unmatched:
        print(f"\n  === 트레일러 없는 VOD ===")
        for aid, name, genre in unmatched:
            print(f"    {genre} | {name[:35]} | {aid[:30]}")


if __name__ == "__main__":
    main()
