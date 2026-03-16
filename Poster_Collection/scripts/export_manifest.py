"""
수집 결과 → Google Drive 전달용 매니페스트 CSV 생성.

실행:
    python Poster_Collection/scripts/export_manifest.py
    python Poster_Collection/scripts/export_manifest.py --only-downloaded  # 다운로드 성공 행만
    python Poster_Collection/scripts/export_manifest.py --out custom.csv
"""
import sys
import os
import csv
import argparse
import logging
from datetime import datetime

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_MODULE_DIR = os.path.join(_root, "Poster_Collection")
_DATA_DIR = os.path.join(_MODULE_DIR, "data")
MANIFEST_PATH = os.path.join(_DATA_DIR, "manifest.csv")
MANIFEST_HEADER = ["series_id", "series_nm", "local_path", "naver_url", "downloaded_at"]


def load_manifest(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def export_manifest(rows: list[dict], out_path: str):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_HEADER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Google Drive 전달용 매니페스트 생성")
    parser.add_argument("--only-downloaded", action="store_true", help="다운로드 성공 행만 포함")
    parser.add_argument("--out", type=str, default="", help="출력 파일 경로 (기본: data/export_YYYYMMDD_HHMMSS.csv)")
    args = parser.parse_args()

    rows = load_manifest(MANIFEST_PATH)
    if not rows:
        logger.error("매니페스트가 없습니다: %s", MANIFEST_PATH)
        sys.exit(1)

    logger.info("매니페스트 로드: %d행", len(rows))

    if args.only_downloaded:
        rows = [r for r in rows if r.get("local_path")]
        logger.info("다운로드 성공 필터 후: %d행", len(rows))

    if args.out:
        out_path = args.out
    else:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(_DATA_DIR, f"export_{ts}.csv")

    export_manifest(rows, out_path)

    total = len(rows)
    dl_ok = sum(1 for r in rows if r.get("local_path"))
    logger.info("내보내기 완료: %s", out_path)
    logger.info("  전체 행: %d / 다운로드 성공: %d / 실패(URL만): %d", total, dl_ok, total - dl_ok)


if __name__ == "__main__":
    main()
