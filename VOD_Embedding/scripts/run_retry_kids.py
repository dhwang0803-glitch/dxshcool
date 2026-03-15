"""
키즈 크롤링 실패 건 재시도 파이프라인 (2분할 병렬)

crawl_trailers(--retry-failed) → batch_embed → ingest_to_db
※ propagate는 마지막에 1회 실행

실행:
    python scripts/run_retry_kids.py                     # 2분할 병렬
    python scripts/run_retry_kids.py --partition K1      # K1만 단독
    python scripts/run_retry_kids.py --start-from embed  # 크롤 완료 후 임베딩부터
    python scripts/run_retry_kids.py --dry-run --limit 3

로그:
    data/retry_kids_K1.log / retry_kids_K2.log
"""

import sys
import json
import subprocess
import threading
import argparse
import logging
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
SCRIPTS_DIR  = Path(__file__).parent
PYTHON       = sys.executable
PARTITIONS   = ["K1", "K2", "K3"]

# 원본 crawl_status (키즈 파이프라인이 쓴 파일)
SOURCE_STATUS = DATA_DIR / "crawl_status.json"


# ── 유틸 ──────────────────────────────────────────────────────────────

def partition_paths(p: str) -> dict:
    return {
        "task_file":    DATA_DIR / f"tasks_retry_kids_{p}.json",
        "crawl_status": DATA_DIR / f"crawl_status_retry_{p}.json",
        "embed_status": DATA_DIR / f"embed_status_retry_{p}.json",
        "parquet_out":  DATA_DIR / f"embeddings_retry_kids_{p}.parquet",
        "log":          DATA_DIR / f"retry_kids_{p}.log",
    }


def setup_logger(log_path: Path, name: str) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        sh = logging.StreamHandler(sys.stdout)
        fh = logging.FileHandler(log_path, encoding='utf-8')
        sh.setFormatter(fmt)
        fh.setFormatter(fmt)
        logger.addHandler(sh)
        logger.addHandler(fh)
    return logger


def run_step(name: str, cmd: list, log: logging.Logger) -> bool:
    log.info(f"=== {name} 시작 ===")
    log.info(f"CMD: {' '.join(str(c) for c in cmd)}")
    start = datetime.now()
    proc  = subprocess.run(cmd, encoding='utf-8', errors='replace')
    elapsed = int((datetime.now() - start).total_seconds())
    if proc.returncode == 0:
        log.info(f"=== {name} 완료 ({elapsed // 60}분 {elapsed % 60}초) ===\n")
        return True
    log.error(f"=== {name} 실패 (exit={proc.returncode}) ===\n")
    return False


# ── 분할 파일 생성 ──────────────────────────────────────────────────

def split_failed_tasks(log: logging.Logger):
    """crawl_status.json의 failed 키즈 항목 → tasks_retry_kids_K1/K2.json"""
    paths = [partition_paths(p)["task_file"] for p in PARTITIONS]
    if all(p.exists() for p in paths):
        log.info("분할 파일 이미 존재 — 스킵")
        return

    if not SOURCE_STATUS.exists():
        log.error(f"원본 상태 파일 없음: {SOURCE_STATUS}")
        return

    with open(SOURCE_STATUS, encoding='utf-8') as f:
        status = json.load(f)

    tasks = [
        {
            "vod_id":       vod_id,
            "asset_nm":     v.get("asset_nm", ""),
            "ct_cl":        v.get("ct_cl", "키즈"),
            "series_nm":    v.get("series_nm"),
            "provider":     v.get("provider"),
            "release_date": v.get("release_date"),
        }
        for vod_id, v in status.get("vods", {}).items()
        if isinstance(v, dict)
        and v.get("status") in ("failed", "skipped")
        and v.get("ct_cl") == "키즈"
    ]

    n     = len(tasks)
    size  = n // 3
    splits = [tasks[:size], tasks[size:size*2], tasks[size*2:]]

    for p, chunk in zip(PARTITIONS, splits):
        out = partition_paths(p)["task_file"]
        payload = {
            "description": f"키즈 크롤링 실패 재시도 파티션 {p}",
            "total": len(chunk),
            "tasks": chunk,
        }
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log.info(f"  {out.name}: {len(chunk)}건")

    log.info(f"분할 완료: 실패 {n}건 → K1/K2")


# ── 파티션 실행 ─────────────────────────────────────────────────────

def run_partition(p: str, args, log: logging.Logger):
    paths     = partition_paths(p)
    stages    = ['crawl', 'embed', 'ingest']
    start_idx = stages.index(args.start_from)

    log.info("=" * 60)
    log.info(f"파티션 {p} 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 60)

    # STEP 1: crawl (propagate 없이)
    if start_idx <= 0:
        cmd = [
            PYTHON, str(SCRIPTS_DIR / "crawl_trailers.py"),
            "--task-file",   str(paths["task_file"]),
            "--status-file", str(paths["crawl_status"]),
        ]
        if args.dry_run: cmd.append("--dry-run")
        if args.limit:   cmd += ["--limit", str(args.limit)]
        if not run_step(f"[{p}] STEP 1: crawl_trailers", cmd, log):
            log.error(f"[{p}] 크롤링 실패 — 중단")
            return False

    # STEP 2: embed
    if start_idx <= 1:
        cmd = [
            PYTHON, str(SCRIPTS_DIR / "batch_embed.py"),
            "--output",            "parquet",
            "--out-file",          str(paths["parquet_out"]),
            "--crawl-status-file", str(paths["crawl_status"]),
            "--embed-status-file", str(paths["embed_status"]),
            "--delete-after-embed",
        ]
        if not run_step(f"[{p}] STEP 2: batch_embed", cmd, log):
            log.error(f"[{p}] 임베딩 실패 — 중단")
            return False

        if not args.dry_run and not paths["parquet_out"].exists():
            log.warning(f"[{p}] parquet 없음 (성공 건 0일 수 있음)")
            return True

    # STEP 3: ingest (propagate 없음 — 메인에서 일괄)
    if start_idx <= 2:
        pq = paths["parquet_out"]
        if not args.dry_run and not pq.exists():
            log.warning(f"[{p}] parquet 없음, ingest 건너뜀")
        else:
            cmd = [PYTHON, str(SCRIPTS_DIR / "ingest_to_db.py"), "--file", str(pq)]
            if args.dry_run: cmd.append("--dry-run")
            if not run_step(f"[{p}] STEP 3: ingest_to_db", cmd, log):
                log.error(f"[{p}] DB 적재 실패")
                return False

    log.info(f"[{p}] 파티션 완료: {datetime.now():%Y-%m-%d %H:%M:%S}")
    return True


# ── 메인 ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="키즈 재시도 파이프라인 (2분할)")
    parser.add_argument('--partition',  type=str, default='',
                        choices=['', 'K1', 'K2', 'K3'])
    parser.add_argument('--start-from', type=str, default='crawl',
                        choices=['crawl', 'embed', 'ingest'])
    parser.add_argument('--dry-run',    action='store_true')
    parser.add_argument('--limit',      type=int, default=0)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    main_log = setup_logger(DATA_DIR / "retry_kids_main.log", "retry_kids_main")
    main_log.info("=" * 60)
    main_log.info(f"키즈 재시도 파이프라인 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    main_log.info("=" * 60)

    if args.start_from == 'crawl':
        split_failed_tasks(main_log)

    if args.partition:
        log = setup_logger(partition_paths(args.partition)["log"], f"retry_{args.partition}")
        run_partition(args.partition, args, log)
    else:
        threads = []
        for p in PARTITIONS:
            log = setup_logger(partition_paths(p)["log"], f"retry_{p}")
            t = threading.Thread(target=run_partition, args=(p, args, log),
                                 name=f"partition_{p}", daemon=True)
            threads.append(t)

        main_log.info("3분할 병렬 실행 (K1/K2/K3)")
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # K1/K2 완료 후 propagate 1회 실행
    if not args.partition and not args.dry_run and args.start_from in ('crawl', 'embed', 'ingest'):
        main_log.info("=== propagate 실행 ===")
        run_step("propagate", [PYTHON, str(SCRIPTS_DIR / "ingest_to_db.py"), "--propagate"], main_log)

    main_log.info(f"전체 완료: {datetime.now():%Y-%m-%d %H:%M:%S}")


if __name__ == "__main__":
    main()
