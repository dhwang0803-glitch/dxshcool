"""
DB poster_url 업데이트 실행 스크립트 (관리자 전용).

실행:
    python Poster_Collection/scripts/update_poster_url.py \
        --manifest data/manifest.csv \
        --vpc-map vpc_paths.csv

vpc_paths.csv 형식:
    series_id,vpc_url
    10001,https://cdn.example.com/posters/10001.jpg
    ...
"""
import sys
import os
import csv
import argparse
import logging

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

import psycopg2
from Poster_Collection.src import db_updater

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_mapping(manifest_path: str, vpc_map_path: str) -> dict:
    """
    manifest CSV + vpc_map CSV → {series_nm: vpc_url} 매핑 생성.

    manifest: series_id, series_nm, local_path, naver_url, downloaded_at
    vpc_map:  series_id, vpc_url
    """
    # series_id → series_nm (manifest에서)
    id_to_nm: dict[str, str] = {}
    with open(manifest_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = str(row["series_id"])
            if sid not in id_to_nm:
                id_to_nm[sid] = row["series_nm"]

    # series_id → vpc_url (vpc_map에서)
    mapping: dict[str, str] = {}
    with open(vpc_map_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = str(row["series_id"])
            vpc_url = row.get("vpc_url", "").strip()
            if not vpc_url:
                continue
            series_nm = id_to_nm.get(sid)
            if series_nm:
                mapping[series_nm] = vpc_url
            else:
                logger.warning("vpc_map에 series_id=%s가 manifest에 없음 — 스킵", sid)

    return mapping


def main():
    parser = argparse.ArgumentParser(description="DB poster_url 업데이트 (관리자 전용)")
    parser.add_argument("--manifest", required=True, help="매니페스트 CSV 경로")
    parser.add_argument("--vpc-map", required=True, help="VPC 업로드 경로 매핑 CSV (series_id, vpc_url)")
    parser.add_argument("--dry-run", action="store_true", help="DB 변경 없이 매핑만 출력")
    args = parser.parse_args()

    for path in (args.manifest, args.vpc_map):
        if not os.path.exists(path):
            logger.error("파일을 찾을 수 없습니다: %s", path)
            sys.exit(1)

    logger.info("매핑 로드 중...")
    mapping = load_mapping(args.manifest, args.vpc_map)
    logger.info("매핑 완료: %d건 (series_nm → vpc_url)", len(mapping))

    if args.dry_run:
        for nm, url in list(mapping.items())[:5]:
            logger.info("  [DRY-RUN] %s → %s", nm, url)
        if len(mapping) > 5:
            logger.info("  ... 외 %d건", len(mapping) - 5)
        sys.exit(0)

    logger.info("DB 연결 중...")
    conn = get_db_conn()
    try:
        total = db_updater.update_poster_urls(conn, mapping)
        logger.info("업데이트 완료: 총 %d행", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
