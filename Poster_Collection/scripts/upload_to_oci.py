"""
manifest CSV의 로컬 포스터 파일을 OCI Object Storage에 업로드하고
oci_map.csv (series_id, oci_url)를 출력한다.

실행:
    python Poster_Collection/scripts/upload_to_oci.py \
        --manifest data/manifest.csv \
        --out data/oci_map.csv

    # 이미 업로드된 항목 건너뛰기 (재실행 안전)
    python Poster_Collection/scripts/upload_to_oci.py \
        --manifest data/manifest.csv \
        --out data/oci_map.csv \
        --skip-existing

    # 실행 후 바로 DB 업데이트까지
    python Poster_Collection/scripts/upload_to_oci.py \
        --manifest data/manifest.csv \
        --out data/oci_map.csv \
        --update-db

환경변수 (.env 필수):
    OCI_NAMESPACE, OCI_BUCKET_NAME, OCI_REGION
    OCI_CONFIG_PROFILE (선택, 기본 DEFAULT)
    DB_* (--update-db 사용 시)
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

from Poster_Collection.src import oci_uploader, db_updater
import psycopg2

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_manifest(manifest_path: str) -> list[dict]:
    """manifest CSV → 행 목록 반환. (series_id, season) 중복은 첫 번째만 사용."""
    seen = set()
    rows = []
    with open(manifest_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            sid = str(row["series_id"])
            season = row.get("season", "1")
            key = (sid, season)
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return rows


def write_oci_map(out_path: str, records: list[dict]):
    """oci_map.csv 저장 (series_id, series_nm, season, oci_url)."""
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["series_id", "series_nm", "season", "oci_url"])
        writer.writeheader()
        writer.writerows(records)


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def main():
    parser = argparse.ArgumentParser(description="포스터 → OCI Object Storage 업로드")
    parser.add_argument("--manifest", required=True, help="매니페스트 CSV 경로")
    parser.add_argument("--out", required=True, help="oci_map.csv 출력 경로")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="OCI에 이미 존재하는 오브젝트는 업로드 건너뜀 (재실행 안전)",
    )
    parser.add_argument(
        "--update-db",
        action="store_true",
        help="업로드 완료 후 vod.poster_url DB 업데이트까지 수행",
    )
    parser.add_argument("--dry-run", action="store_true", help="실제 업로드 없이 대상만 출력")
    parser.add_argument("--part", type=int, default=1, help="분할 번호 (1-based, 기본: 1)")
    parser.add_argument("--total-parts", type=int, default=1, help="총 분할 수 (기본: 1=단일)")
    args = parser.parse_args()

    if not os.path.exists(args.manifest):
        logger.error("manifest 파일을 찾을 수 없음: %s", args.manifest)
        sys.exit(1)

    all_rows = load_manifest(args.manifest)
    logger.info("매니페스트 로드: %d개 시리즈", len(all_rows))

    # 분할 슬라이싱
    if args.total_parts > 1:
        import math
        chunk = math.ceil(len(all_rows) / args.total_parts)
        start = (args.part - 1) * chunk
        rows = all_rows[start: start + chunk]
        logger.info("분할 %d/%d: %d건 담당", args.part, args.total_parts, len(rows))
    else:
        rows = all_rows

    success, skipped, failed = [], 0, 0
    oci_records = []

    for i, row in enumerate(rows, 1):
        sid = str(row["series_id"])
        series_nm = row.get("series_nm", sid)
        season = row.get("season", "1")
        local_path = row.get("local_path", "")
        suffix = os.path.splitext(local_path)[1] or ".jpg"
        object_name = f"{sid}{suffix}"

        if args.dry_run:
            logger.info("[DRY-RUN] %d/%d  %s → %s", i, len(rows), local_path, object_name)
            continue

        # 이미 업로드된 경우 스킵
        if args.skip_existing:
            try:
                if oci_uploader.object_exists(object_name):
                    region = os.getenv("OCI_REGION")
                    namespace = os.getenv("OCI_NAMESPACE")
                    bucket = os.getenv("OCI_BUCKET_NAME")
                    url = oci_uploader.build_public_url(region, namespace, bucket, object_name)
                    oci_records.append({"series_id": sid, "series_nm": series_nm, "season": season, "oci_url": url})
                    skipped += 1
                    continue
            except Exception as e:
                logger.warning("[%d/%d] 존재 확인 실패 %s: %s — 재업로드 시도", i, len(rows), sid, e)

        try:
            url = oci_uploader.upload_file(local_path, object_name)
            oci_records.append({"series_id": sid, "series_nm": series_nm, "season": season, "oci_url": url})
            success.append(sid)
            logger.info("[%d/%d] OK  %s", i, len(rows), object_name)
        except FileNotFoundError:
            logger.warning("[%d/%d] SKIP 로컬 파일 없음: %s", i, len(rows), local_path)
            failed += 1
        except Exception as e:
            logger.error("[%d/%d] FAIL %s: %s", i, len(rows), sid, e)
            failed += 1

    if args.dry_run:
        return

    # 파트별 출력 파일 (1분할 포함 항상 적용)
    base, ext = os.path.splitext(args.out)
    out_path = f"{base}_part{args.part}{ext}"

    write_oci_map(out_path, oci_records)
    logger.info(
        "oci_map.csv 저장: %s  (성공=%d, 스킵=%d, 실패=%d)",
        out_path,
        len(success),
        skipped,
        failed,
    )

    if args.update_db and oci_records:
        logger.info("DB 업데이트 시작 (시즌별)...")
        from Poster_Collection.src.tving_poster import parse_season_from_asset_nm
        season_mapping = {
            (r["series_nm"], int(r["season"])): r["oci_url"]
            for r in oci_records
        }
        conn = get_db_conn()
        try:
            total = db_updater.update_poster_urls_by_season(
                conn, season_mapping, parse_season_from_asset_nm,
            )
            logger.info("DB 업데이트 완료: %d행", total)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
