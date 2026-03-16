"""
DB poster_url 업데이트 실행 스크립트 (관리자 전용).

실행:
    python Poster_Collection/scripts/update_poster_url.py \
        --manifest data/manifest.csv \
        --oci-map data/oci_map.csv

oci_map.csv 형식 (upload_to_oci.py 출력):
    series_id,series_nm,oci_url
    10001,이상한변호사우영우,https://objectstorage.ap-chuncheon-1.oraclecloud.com/n/.../b/vod-posters/o/10001.jpg
    ...

※ upload_to_oci.py --update-db 옵션을 쓰면 이 스크립트를 별도 실행할 필요 없음.
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


def load_mapping(manifest_path: str, oci_map_path: str) -> dict:
    """
    oci_map CSV → {series_nm: oci_url} 매핑 생성.

    oci_map (upload_to_oci.py 출력): series_id, series_nm, oci_url
    manifest: series_id, series_nm, local_path, naver_url, downloaded_at
              (series_nm이 oci_map에 없을 때 폴백으로 사용)
    """
    # series_id → series_nm 폴백 (manifest에서)
    id_to_nm: dict[str, str] = {}
    with open(manifest_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = str(row["series_id"])
            if sid not in id_to_nm:
                id_to_nm[sid] = row["series_nm"]

    # oci_map에서 매핑 구성
    mapping: dict[str, str] = {}
    with open(oci_map_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = str(row["series_id"])
            oci_url = row.get("oci_url", "").strip()
            if not oci_url:
                continue
            # oci_map에 series_nm이 있으면 직접 사용, 없으면 manifest 폴백
            series_nm = row.get("series_nm", "").strip() or id_to_nm.get(sid)
            if series_nm:
                mapping[series_nm] = oci_url
            else:
                logger.warning("series_id=%s의 series_nm을 찾을 수 없음 — 스킵", sid)

    return mapping


def main():
    parser = argparse.ArgumentParser(description="DB poster_url 업데이트 (관리자 전용)")
    parser.add_argument("--manifest", required=True, help="매니페스트 CSV 경로")
    parser.add_argument("--oci-map", required=True, help="OCI 업로드 결과 CSV (upload_to_oci.py 출력: series_id, series_nm, oci_url)")
    parser.add_argument("--dry-run", action="store_true", help="DB 변경 없이 매핑만 출력")
    args = parser.parse_args()

    for path in (args.manifest, args.oci_map):
        if not os.path.exists(path):
            logger.error("파일을 찾을 수 없습니다: %s", path)
            sys.exit(1)

    logger.info("매핑 로드 중...")
    mapping = load_mapping(args.manifest, args.oci_map)
    logger.info("매핑 완료: %d건 (series_nm → oci_url)", len(mapping))

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
