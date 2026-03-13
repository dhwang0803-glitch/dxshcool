"""
오늘 크롤링된 success 항목 초기화 스크립트

title_matches 버그(series 미전달)로 인해 오늘 잘못 매칭된 항목을 리셋.
downloaded_at 기준 오늘(2026-03-13T16: 이후) success 항목만 제거 → 재수집 대상이 됨.

실행:
    cd VOD_Embedding
    python scripts/reset_today_crawl.py --dry-run  # 확인
    python scripts/reset_today_crawl.py            # 실행
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

RESET_AFTER = "2026-03-13T23:11:"  # 23:11 재시작 이후 (회차 검증 없는 버전으로 크롤된 항목)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    with open(STATUS_FILE, encoding='utf-8') as f:
        data = json.load(f)
    vods = data.get("vods", {})

    reset_ids = []
    for vod_id, info in vods.items():
        if info.get("status") != "success":
            continue
        downloaded_at = info.get("downloaded_at", "")
        if downloaded_at >= RESET_AFTER:
            reset_ids.append(vod_id)

    print(f"리셋 대상 (오늘 {RESET_AFTER} 이후 success): {len(reset_ids):,}건")
    for vid in reset_ids[:20]:
        print(f"  {vid}: {vods[vid].get('asset_nm')} → {vods[vid].get('filename')}")
    if len(reset_ids) > 20:
        print(f"  ... 외 {len(reset_ids)-20}건")

    if args.dry_run:
        print("[DRY-RUN] 변경 없이 종료")
        return

    # 파일도 함께 삭제
    deleted_files = 0
    for vod_id in reset_ids:
        fname = vods[vod_id].get("filename", "")
        if fname:
            fpath = TRAILERS_DIR / fname
            if fpath.exists():
                fpath.unlink()
                deleted_files += 1
        del vods[vod_id]

    data["vods"] = vods
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"{len(reset_ids):,}건 초기화 완료 (파일 삭제: {deleted_files}개) → 재수집 대상으로 전환")


if __name__ == "__main__":
    main()
