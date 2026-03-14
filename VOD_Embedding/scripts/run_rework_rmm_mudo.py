"""
런닝맨 Classic + 무한도전 Classic 재작업 파이프라인 (3분할 병렬)

crawl_trailers → batch_embed → ingest_to_db
※ propagate 실행 안 함 (에피소드 단위이므로)

실행:
    python scripts/run_rework_rmm_mudo.py                      # 전체 3분할 병렬
    python scripts/run_rework_rmm_mudo.py --partition R1       # R1만 단독
    python scripts/run_rework_rmm_mudo.py --start-from embed   # 크롤 완료 후 임베딩부터
    python scripts/run_rework_rmm_mudo.py --start-from ingest  # 임베딩 완료 후 적재만
    python scripts/run_rework_rmm_mudo.py --dry-run --limit 3  # 동작 확인

로그:
    data/rework_R1.log / rework_R2.log / rework_R3.log
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

SOURCE_TASK  = DATA_DIR / "tasks_rework_rmm_mudo.json"
PARTITIONS   = ["R1", "R2", "R3"]


# ── 유틸 ──────────────────────────────────────────────────────────────

def partition_paths(p: str) -> dict:
    return {
        "task_file":    DATA_DIR / f"tasks_rework_{p}.json",
        "crawl_status": DATA_DIR / f"crawl_status_rework_{p}.json",
        "embed_status": DATA_DIR / f"embed_status_rework_{p}.json",
        "parquet_out":  DATA_DIR / f"embeddings_rework_{p}.parquet",
        "log":          DATA_DIR / f"rework_{p}.log",
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

def split_tasks(log: logging.Logger):
    """tasks_rework_rmm_mudo.json → tasks_rework_R1/R2/R3.json"""
    # 이미 분할된 경우 스킵
    paths = [partition_paths(p)["task_file"] for p in PARTITIONS]
    if all(p.exists() for p in paths):
        log.info("분할 파일 이미 존재 — 스킵")
        return

    with open(SOURCE_TASK, encoding='utf-8') as f:
        data = json.load(f)
    tasks  = data["tasks"]
    n      = len(tasks)
    size   = n // 3
    splits = [tasks[:size], tasks[size:size * 2], tasks[size * 2:]]

    for p, chunk in zip(PARTITIONS, splits):
        out = partition_paths(p)["task_file"]
        payload = {
            "description": f"런닝맨+무한도전 Classic 재작업 파티션 {p}",
            "total": len(chunk),
            "tasks": chunk,
        }
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        log.info(f"  {out.name}: {len(chunk)}건")

    log.info(f"분할 완료: 총 {n}건 → 3파티션")


# ── 파티션 실행 ─────────────────────────────────────────────────────

def run_partition(p: str, args, log: logging.Logger):
    paths     = partition_paths(p)
    stages    = ['crawl', 'embed', 'ingest']
    start_idx = stages.index(args.start_from)

    log.info("=" * 60)
    log.info(f"파티션 {p} 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 60)

    # STEP 1: crawl
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
            log.error(f"[{p}] parquet 없음: {paths['parquet_out']}")
            return False

    # STEP 3: ingest (propagate 없음)
    if start_idx <= 2:
        pq = paths["parquet_out"]
        if not args.dry_run and not pq.exists():
            log.warning(f"[{p}] parquet 없음, ingest 건너뜀: {pq}")
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
    parser = argparse.ArgumentParser(description="런닝맨+무한도전 Classic 재작업 파이프라인")
    parser.add_argument('--partition',  type=str, default='',
                        choices=['', 'R1', 'R2', 'R3'],
                        help='단독 파티션 실행 (기본: 3개 병렬)')
    parser.add_argument('--start-from', type=str, default='crawl',
                        choices=['crawl', 'embed', 'ingest'])
    parser.add_argument('--dry-run',    action='store_true')
    parser.add_argument('--limit',      type=int, default=0)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 공통 로거 (split 로그용)
    main_log = setup_logger(DATA_DIR / "rework_main.log", "rework_main")
    main_log.info("=" * 60)
    main_log.info(f"재작업 파이프라인 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    main_log.info(f"start_from={args.start_from} / dry_run={args.dry_run} / limit={args.limit}")
    main_log.info("=" * 60)

    # 분할 파일 생성 (crawl 단계에서만)
    if args.start_from == 'crawl':
        split_tasks(main_log)

    # 단독 파티션 실행
    if args.partition:
        log = setup_logger(partition_paths(args.partition)["log"], f"rework_{args.partition}")
        run_partition(args.partition, args, log)
        return

    # 3파티션 병렬 실행
    threads = []
    for p in PARTITIONS:
        log = setup_logger(partition_paths(p)["log"], f"rework_{p}")
        t = threading.Thread(
            target=run_partition,
            args=(p, args, log),
            name=f"partition_{p}",
            daemon=True,
        )
        threads.append(t)

    main_log.info("3파티션 병렬 실행 시작 (R1/R2/R3)")
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    main_log.info("=" * 60)
    main_log.info(f"전체 완료: {datetime.now():%Y-%m-%d %H:%M:%S}")
    main_log.info("=" * 60)


if __name__ == "__main__":
    main()
