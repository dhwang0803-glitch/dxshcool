"""
phantom-success 초기화 스크립트

crawl_status_아름.json에서 status=success이지만 실제 파일이 없는 항목을
unprocessed 상태로 리셋 → crawl_trailers_아름.py 재수집 가능하게 함

실행:
    cd VOD_Embedding
    python scripts/reset_phantom_crawl.py          # 실제 초기화
    python scripts/reset_phantom_crawl.py --dry-run  # 확인만
"""

import sys
import json
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
TRAILERS_DIR = DATA_DIR / "trailers_아름"
STATUS_FILE  = DATA_DIR / "crawl_status_아름.json"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='변경 없이 현황만 출력')
    args = parser.parse_args()

    with open(STATUS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    vods = data.get("vods", {})

    phantom_ids = []
    for vod_id, info in vods.items():
        if info.get("status") != "success":
            continue
        fname = info.get("filename", "")
        if not (TRAILERS_DIR / fname).exists():
            phantom_ids.append(vod_id)

    print(f"phantom-success (파일 없음): {len(phantom_ids):,}건")

    if args.dry_run:
        print("[DRY-RUN] 변경 없이 종료")
        return

    # 초기화: vods 딕셔너리에서 제거 → 재수집 대상이 됨
    for vod_id in phantom_ids:
        del vods[vod_id]

    data["vods"]     = vods
    data["success"]  = data.get("success", 0) - len(phantom_ids)
    data["processed"] = data.get("processed", 0) - len(phantom_ids)

    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"{len(phantom_ids):,}건 초기화 완료 → crawl_trailers_아름.py 재실행하세요")


if __name__ == "__main__":
    main()
