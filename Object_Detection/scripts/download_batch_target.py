"""
download_batch_target.py — 조장님 지정 19개 영상 다운로드

실행:
    cd Object_Detection
    python scripts/download_batch_target.py
    python scripts/download_batch_target.py --dry-run    # URL 확인만
    python scripts/download_batch_target.py --limit 3     # 3개만
"""
import sys
import subprocess
import argparse
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "batch_target"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 다운로드 대상 목록 ──────────────────────────────────────────────
TARGETS = [
    # 여행 — 동원아 여행가자
    {"id": "travel_dongwon_06", "title": "동원아여행가자_06_영월", "genre": "여행",
     "url": "https://youtu.be/fUDjJKcacdU"},
    {"id": "travel_dongwon_11", "title": "동원아여행가자_11_정선", "genre": "여행",
     "url": "https://youtu.be/sQEhu9y29qQ"},
    {"id": "travel_dongwon_12", "title": "동원아여행가자_12_삼척", "genre": "여행",
     "url": "https://youtu.be/8Q2kdaToxk0"},
    {"id": "travel_dongwon_16", "title": "동원아여행가자_16_제주", "genre": "여행",
     "url": "https://youtu.be/KGjxaD-rdg0"},
    {"id": "travel_dongwon_15", "title": "동원아여행가자_15_소고기", "genre": "여행",
     "url": "https://youtu.be/pyraZGbe4y0"},
    # 여행 — 서울촌놈
    {"id": "travel_chonnom_01", "title": "서울촌놈_01_부산", "genre": "여행",
     "url": "https://youtu.be/fqtBOF8kJrQ"},
    {"id": "travel_chonnom_03", "title": "서울촌놈_03_광주", "genre": "여행",
     "url": "https://youtu.be/mQXHy_ScL5I"},
    {"id": "travel_chonnom_05", "title": "서울촌놈_05_청주", "genre": "여행",
     "url": "https://youtu.be/kcJuGQAGJGA"},
    {"id": "travel_chonnom_07", "title": "서울촌놈_07_대전", "genre": "여행",
     "url": "https://youtu.be/-MM4DK5mW68"},
    {"id": "travel_chonnom_09", "title": "서울촌놈_09_전주", "genre": "여행",
     "url": "https://youtu.be/WLNlIm6UMm0"},
    # 음식_먹방 — 알토란
    {"id": "food_altoran_490", "title": "알토란_490_배추김치", "genre": "음식_먹방",
     "url": "https://youtu.be/YkFCNmqNg4k"},
    {"id": "food_altoran_418", "title": "알토란_418_궁중동치미", "genre": "음식_먹방",
     "url": "https://youtu.be/nz3ZeYyBVSQ"},
    {"id": "food_altoran_440", "title": "알토란_440_한우화산불고기", "genre": "음식_먹방",
     "url": "https://youtu.be/gjbXH09tZSw"},
    {"id": "food_altoran_496", "title": "알토란_496_순두부", "genre": "음식_먹방",
     "url": "https://youtu.be/O2QvRLsNcrQ"},
    # 음식_먹방 — 로컬식탁 (네이버)
    {"id": "food_local_memill", "title": "로컬식탁_강원메밀막국수", "genre": "음식_먹방",
     "url": "https://naver.me/GDQeRuuq"},
    {"id": "food_local_keyjo", "title": "로컬식탁_보령키조개", "genre": "음식_먹방",
     "url": "https://naver.me/xvC7elsP"},
    {"id": "food_local_samchi", "title": "로컬식탁_삼치회", "genre": "음식_먹방",
     "url": "https://naver.me/5WUlktId"},
    {"id": "food_local_sugyuk", "title": "로컬식탁_원산도수육국수", "genre": "음식_먹방",
     "url": "https://naver.me/x3cg4VSB"},
    {"id": "food_local_dakgalbi", "title": "로컬식탁_춘천닭갈비", "genre": "음식_먹방",
     "url": "https://naver.me/5wrCI9fd"},
]


def download(url, output_path):
    cmd = [
        "yt-dlp",
        "-f", "best[height<=720]",
        "--merge-output-format", "mp4",
        "-o", str(output_path),
        "--no-playlist",
        url,
    ]
    try:
        result = subprocess.run(cmd, timeout=600)
        return result.returncode == 0 and output_path.exists()
    except subprocess.TimeoutExpired:
        print(f"  ❌ 타임아웃")
        return False


def main():
    parser = argparse.ArgumentParser(description="대상 19개 영상 다운로드")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--genre", type=str, default=None, help="여행 | 음식_먹방")
    args = parser.parse_args()

    targets = TARGETS
    if args.genre:
        targets = [t for t in targets if t["genre"] == args.genre]
    if args.limit > 0:
        targets = targets[:args.limit]

    print(f"{'=' * 60}")
    print(f"  대상: {len(targets)}개")
    print(f"  저장: {OUTPUT_DIR}")
    print(f"  모드: {'DRY-RUN' if args.dry_run else '다운로드'}")
    print(f"{'=' * 60}")

    success = failed = skipped = 0

    for i, t in enumerate(targets):
        output_path = OUTPUT_DIR / f"{t['id']}.mp4"

        if output_path.exists():
            print(f"  [{i+1}/{len(targets)}] 스킵 (있음): {t['title']}")
            skipped += 1
            continue

        print(f"\n  [{i+1}/{len(targets)}] {t['genre']} | {t['title']}")
        print(f"    URL: {t['url']}")

        if args.dry_run:
            success += 1
            continue

        print(f"    다운로드 중...")
        if download(t["url"], output_path):
            size_mb = output_path.stat().st_size / 1024 / 1024
            print(f"    ✅ 완료 ({size_mb:.1f}MB)")
            success += 1
        else:
            print(f"    ❌ 실패")
            failed += 1

    print(f"\n{'=' * 60}")
    print(f"  완료: 성공 {success} / 실패 {failed} / 스킵 {skipped}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
