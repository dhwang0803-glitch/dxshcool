"""
포스터 수집 풀 파이프라인 (4분할 병렬 크롤링 → manifest 통합 → 4분할 병렬 OCI 업로드 → 시즌별 DB 업데이트).

크롤링은 (series_nm, season) 단위로 수행되며, DB 업데이트도 시즌별로 적용된다.

실행:
    python Poster_Collection/scripts/run_full_pipeline.py
    python Poster_Collection/scripts/run_full_pipeline.py --parts 4           # 분할 수 지정 (기본 4)
    python Poster_Collection/scripts/run_full_pipeline.py --skip-crawl        # 크롤링 건너뛰고 통합부터
    python Poster_Collection/scripts/run_full_pipeline.py --skip-oci          # OCI 업로드 건너뛰기
    python Poster_Collection/scripts/run_full_pipeline.py --dry-run           # OCI/DB 변경 없이 크롤링+통합만
"""
import sys
import os
import csv
import glob
import json
import time
import argparse
import logging
import subprocess
from datetime import datetime

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

_MODULE_DIR = os.path.join(_root, "Poster_Collection")
_DATA_DIR = os.path.join(_MODULE_DIR, "data")
_SCRIPTS_DIR = os.path.join(_MODULE_DIR, "scripts")

MANIFEST_HEADER = ["series_id", "series_nm", "season", "local_path", "poster_url", "downloaded_at"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def clean_old_data(parts: int):
    """이전 실행 잔여 파일 정리."""
    patterns = [
        os.path.join(_DATA_DIR, "manifest_part*.csv"),
        os.path.join(_DATA_DIR, "manifest.csv"),
        os.path.join(_DATA_DIR, "crawl_status_part*.json"),
        os.path.join(_DATA_DIR, "crawl_status.json"),
        os.path.join(_DATA_DIR, "crawl_part*.log"),
        os.path.join(_DATA_DIR, "oci_map.csv"),
        os.path.join(_DATA_DIR, "oci_map_part*.csv"),
        os.path.join(_DATA_DIR, "oci_upload_part*.log"),
    ]
    removed = 0
    for pat in patterns:
        for f in glob.glob(pat):
            os.remove(f)
            removed += 1
    if removed:
        logger.info("이전 데이터 %d개 파일 정리 완료", removed)


def run_parallel_crawl(parts: int):
    """crawl_posters.py를 N개 파트로 병렬 실행."""
    crawl_script = os.path.join(_SCRIPTS_DIR, "crawl_posters.py")
    procs = []
    log_files = []

    for i in range(1, parts + 1):
        log_path = os.path.join(_DATA_DIR, f"crawl_part{i}.log")
        log_f = open(log_path, "w", encoding="utf-8")
        log_files.append(log_f)

        cmd = [
            sys.executable, crawl_script,
            "--part", str(i),
            "--total-parts", str(parts),
        ]
        logger.info("파트 %d/%d 시작: %s", i, parts, " ".join(cmd))
        p = subprocess.Popen(
            cmd, stdout=log_f, stderr=subprocess.STDOUT,
            cwd=_root, env=os.environ.copy(),
        )
        procs.append((i, p))

    # 진행 상황 모니터링
    logger.info("=== %d개 프로세스 병렬 실행 중 ===", parts)
    while True:
        alive = [(i, p) for i, p in procs if p.poll() is None]
        if not alive:
            break

        status_parts = []
        for i in range(1, parts + 1):
            cp = os.path.join(_DATA_DIR, f"crawl_status_part{i}.json")
            if os.path.exists(cp):
                try:
                    with open(cp, encoding="utf-8") as f:
                        data = json.load(f)
                    stats = data.get("stats", {})
                    total = stats.get("total", 0)
                    api_ok = stats.get("api_ok", 0)
                    status_parts.append(f"P{i}:{total}건({api_ok}ok)")
                except Exception:
                    status_parts.append(f"P{i}:읽기실패")
            else:
                status_parts.append(f"P{i}:대기")

        logger.info("진행: %s / 실행중 %d개", " | ".join(status_parts), len(alive))
        time.sleep(30)

    for log_f in log_files:
        log_f.close()

    failed = []
    for i, p in procs:
        if p.returncode != 0:
            failed.append(i)
            logger.error("파트 %d 실패 (exit code %d)", i, p.returncode)

    if failed:
        logger.error("실패 파트: %s — 로그 확인: %s/crawl_part{N}.log", failed, _DATA_DIR)
        sys.exit(1)

    logger.info("=== 전체 크롤링 완료 ===")


def merge_manifests(parts: int) -> str:
    """파트별 manifest CSV를 통합. (series_nm, season) 기준 중복 제거."""
    merged_path = os.path.join(_DATA_DIR, "manifest.csv")
    seen_keys = set()
    total_rows = 0

    with open(merged_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=MANIFEST_HEADER)
        writer.writeheader()

        for i in range(1, parts + 1):
            part_path = os.path.join(_DATA_DIR, f"manifest_part{i}.csv")
            if not os.path.exists(part_path):
                logger.warning("파트 %d manifest 없음: %s", i, part_path)
                continue

            with open(part_path, newline="", encoding="utf-8") as in_f:
                reader = csv.DictReader(in_f)
                part_count = 0
                for row in reader:
                    key = (row.get("series_nm", ""), row.get("season", "1"))
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    writer.writerow({k: row.get(k, "") for k in MANIFEST_HEADER})
                    part_count += 1
                    total_rows += 1
                logger.info("파트 %d: %d건 통합", i, part_count)

    logger.info("manifest 통합 완료: %s (%d건, 중복 제거 후)", merged_path, total_rows)

    # 파트별 통계 요약
    total_stats = {"total": 0, "api_ok": 0, "dl_ok": 0, "api_fail": 0, "dl_fail": 0}
    for i in range(1, parts + 1):
        cp = os.path.join(_DATA_DIR, f"crawl_status_part{i}.json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                data = json.load(f)
            stats = data.get("stats", {})
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

    t = total_stats
    if t["total"]:
        logger.info(
            "전체 통계: 처리 %d건 / API 성공 %d (%.1f%%) / 다운로드 성공 %d (%.1f%%)",
            t["total"], t["api_ok"],
            t["api_ok"] / t["total"] * 100,
            t["dl_ok"],
            t["dl_ok"] / t["api_ok"] * 100 if t["api_ok"] else 0,
        )

    return merged_path


def run_parallel_oci_upload(manifest_path: str, parts: int, update_db: bool = True):
    """upload_to_oci.py를 N개 파트로 병렬 실행 후, DB 업데이트는 통합 실행."""
    upload_script = os.path.join(_SCRIPTS_DIR, "upload_to_oci.py")
    oci_map_path = os.path.join(_DATA_DIR, "oci_map.csv")
    procs = []
    log_files = []

    # Step 3a: 병렬 OCI 업로드 (DB 업데이트는 통합 후 별도)
    for i in range(1, parts + 1):
        log_path = os.path.join(_DATA_DIR, f"oci_upload_part{i}.log")
        log_f = open(log_path, "w", encoding="utf-8")
        log_files.append(log_f)

        cmd = [
            sys.executable, upload_script,
            "--manifest", manifest_path,
            "--out", oci_map_path,
            "--skip-existing",
            "--part", str(i),
            "--total-parts", str(parts),
        ]
        logger.info("OCI 파트 %d/%d 시작", i, parts)
        p = subprocess.Popen(
            cmd, stdout=log_f, stderr=subprocess.STDOUT,
            cwd=_root, env=os.environ.copy(),
        )
        procs.append((i, p))

    logger.info("=== OCI %d개 프로세스 병렬 업로드 중 ===", parts)
    while True:
        alive = [(i, p) for i, p in procs if p.poll() is None]
        if not alive:
            break
        logger.info("OCI 업로드 실행중 %d개 파트", len(alive))
        time.sleep(30)

    for log_f in log_files:
        log_f.close()

    failed = []
    for i, p in procs:
        if p.returncode != 0:
            failed.append(i)
            logger.error("OCI 파트 %d 실패 (exit code %d)", i, p.returncode)

    if failed:
        logger.error("OCI 실패 파트: %s", failed)

    # Step 3b: oci_map 파트별 통합
    logger.info("oci_map 통합 중...")
    oci_header = ["series_id", "series_nm", "season", "oci_url"]
    seen = set()
    total = 0

    with open(oci_map_path, "w", newline="", encoding="utf-8") as out_f:
        writer = csv.DictWriter(out_f, fieldnames=oci_header)
        writer.writeheader()
        for i in range(1, parts + 1):
            base, ext = os.path.splitext(oci_map_path)
            part_path = f"{base}_part{i}{ext}"
            if not os.path.exists(part_path):
                logger.warning("OCI 파트 %d oci_map 없음", i)
                continue
            count = 0
            with open(part_path, newline="", encoding="utf-8") as in_f:
                for row in csv.DictReader(in_f):
                    key = (row.get("series_nm", ""), row.get("season", "1"))
                    if key in seen:
                        continue
                    seen.add(key)
                    writer.writerow({k: row.get(k, "") for k in oci_header})
                    count += 1
                    total += 1
            logger.info("OCI 파트 %d: %d건 통합", i, count)

    logger.info("oci_map 통합 완료: %d건", total)

    # Step 3c: 시즌별 DB poster_url 업데이트
    if update_db and total > 0:
        logger.info("DB poster_url 시즌별 업데이트 시작...")
        from Poster_Collection.src.tving_poster import parse_season_from_asset_nm
        from Poster_Collection.src import db_updater
        import psycopg2

        season_mapping = {}
        with open(oci_map_path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                key = (row["series_nm"], int(row.get("season", 1)))
                season_mapping[key] = row["oci_url"]

        conn = psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )
        try:
            updated = db_updater.update_poster_urls_by_season(
                conn, season_mapping, parse_season_from_asset_nm,
            )
            logger.info("DB 업데이트 완료: %d행", updated)
        finally:
            conn.close()

    logger.info("OCI 업로드 + DB 업데이트 완료")


def main():
    parser = argparse.ArgumentParser(description="포스터 수집 풀 파이프라인")
    parser.add_argument("--parts", type=int, default=4, help="분할 수 (기본 4)")
    parser.add_argument("--skip-crawl", action="store_true", help="크롤링 건너뛰고 통합부터 시작")
    parser.add_argument("--skip-oci", action="store_true", help="OCI 업로드/DB 업데이트 건너뛰기")
    parser.add_argument("--dry-run", action="store_true", help="크롤링+통합만 실행 (OCI/DB 변경 없음)")
    args = parser.parse_args()

    from dotenv import load_dotenv
    load_dotenv()

    os.makedirs(_DATA_DIR, exist_ok=True)
    t_start = time.time()

    # Step 1: 크롤링
    if not args.skip_crawl:
        logger.info("=" * 60)
        logger.info("Step 1: 이전 데이터 정리 + %d분할 병렬 크롤링", args.parts)
        logger.info("=" * 60)
        clean_old_data(args.parts)
        run_parallel_crawl(args.parts)
    else:
        logger.info("크롤링 건너뜀 (--skip-crawl)")

    # Step 2: manifest 통합
    logger.info("=" * 60)
    logger.info("Step 2: manifest 통합")
    logger.info("=" * 60)
    manifest_path = merge_manifests(args.parts)

    # Step 3: OCI 업로드 + DB 업데이트 (병렬)
    if not args.skip_oci and not args.dry_run:
        logger.info("=" * 60)
        logger.info("Step 3: %d분할 병렬 OCI 업로드 + 시즌별 DB 업데이트", args.parts)
        logger.info("=" * 60)
        run_parallel_oci_upload(manifest_path, parts=args.parts, update_db=True)
    else:
        logger.info("OCI/DB 업데이트 건너뜀")

    elapsed = time.time() - t_start
    logger.info("=" * 60)
    logger.info("파이프라인 완료: 총 %.1f분 소요", elapsed / 60)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
