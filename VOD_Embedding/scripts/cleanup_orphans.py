"""
고아 파일 정리 스크립트

trailers_아름/ 에 있는 파일 중 crawl_status_아름.json에 success로 등록되지 않은
파일(Ctrl+C 중단 등으로 생긴 고아 파일)을 삭제한다.

실행:
    cd VOD_Embedding
    python scripts/cleanup_orphans.py --dry-run  # 확인
    python scripts/cleanup_orphans.py            # 실행
"""

import sys
import json
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
TRAILERS_DIR = DATA_DIR / "trailers_아름"
STATUS_FILE  = DATA_DIR / "crawl_status_아름.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='삭제 없이 목록만 출력')
    args = parser.parse_args()

    # JSON에 등록된 success 파일명 수집
    valid_filenames = set()
    if STATUS_FILE.exists():
        with open(STATUS_FILE, encoding='utf-8') as f:
            data = json.load(f)
        for info in data.get("vods", {}).values():
            if info.get("status") == "success" and info.get("filename"):
                valid_filenames.add(info["filename"])

    # 디스크의 mp4/webm 파일 중 JSON에 없는 것 = 고아 파일
    orphans = [
        f for f in TRAILERS_DIR.glob("cjc_*.*")
        if f.suffix in ('.mp4', '.webm') and f.name not in valid_filenames
    ]

    print(f"고아 파일: {len(orphans):,}개  (JSON 등록 파일: {len(valid_filenames):,}개)")
    for f in orphans[:20]:
        print(f"  {f.name}")
    if len(orphans) > 20:
        print(f"  ... 외 {len(orphans)-20}개")

    if args.dry_run:
        print("[DRY-RUN] 변경 없이 종료")
        return

    for f in orphans:
        f.unlink()
    print(f"{len(orphans):,}개 삭제 완료")


if __name__ == "__main__":
    main()
