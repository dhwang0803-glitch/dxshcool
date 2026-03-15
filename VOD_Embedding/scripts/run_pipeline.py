"""
전체 임베딩 파이프라인 순차 실행 (파티션별 병렬 지원)
crawl_trailers → batch_embed → ingest_to_db (+ propagate + normalize)

실행:
    # 단일 실행
    python scripts/run_pipeline.py --task-file data/tasks_missing.json

    # 3분할 병렬 실행 (터미널 3개에서 각각 실행)
    python scripts/run_pipeline.py --partition P1
    python scripts/run_pipeline.py --partition P2
    python scripts/run_pipeline.py --partition P3

    # 크롤 완료 후 임베딩부터 이어서
    python scripts/run_pipeline.py --partition P1 --start-from embed

    # 임베딩 완료 후 DB 적재 (3개 parquet 한 번에)
    python scripts/run_pipeline.py --start-from ingest --merge-partitions

    # 동작 확인
    python scripts/run_pipeline.py --partition P1 --dry-run --limit 3

로그:
    data/pipeline_P1.log / pipeline_P2.log / pipeline_P3.log
    data/pipeline.log (단일 실행)
"""

import sys
import subprocess
import argparse
import logging
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
PYTHON       = sys.executable
SCRIPTS_DIR  = Path(__file__).parent


def partition_paths(partition: str) -> dict:
    """파티션별 파일 경로 딕셔너리"""
    sfx = f"_{partition}" if partition else ""
    return {
        "task_file":         DATA_DIR / f"tasks_missing{sfx}.json",
        "crawl_status":      DATA_DIR / f"crawl_status{sfx}.json",
        "embed_status":      DATA_DIR / f"embed_status{sfx}.json",
        "parquet_out":       DATA_DIR / f"embeddings_missing{sfx}.parquet",
        "pipeline_log":      DATA_DIR / f"pipeline{sfx}.log",
    }


def setup_logger(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(str(log_path))
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        sh  = logging.StreamHandler(sys.stdout)
        fh  = logging.FileHandler(log_path, encoding='utf-8')
        sh.setFormatter(fmt); fh.setFormatter(fmt)
        logger.addHandler(sh); logger.addHandler(fh)
    return logger


def run_step(name: str, cmd: list, log: logging.Logger) -> bool:
    log.info(f"=== {name} 시작 ===")
    log.info(f"CMD: {' '.join(str(c) for c in cmd)}")
    start = datetime.now()
    proc  = subprocess.run(cmd, encoding='utf-8', errors='replace')
    elapsed = int((datetime.now() - start).total_seconds())
    if proc.returncode == 0:
        log.info(f"=== {name} 완료 ({elapsed//60}분 {elapsed%60}초) ===\n")
        return True
    log.error(f"=== {name} 실패 (exit={proc.returncode}) ===\n")
    return False


def run_partition(paths: dict, args, log: logging.Logger):
    """crawl → embed 순서로 파티션 1개 처리"""
    stages    = ['crawl', 'embed', 'ingest']
    start_idx = stages.index(args.start_from)

    # ── STEP 1: crawl ────────────────────────────────────────────
    if start_idx <= 0:
        cmd = [PYTHON, str(SCRIPTS_DIR / "crawl_trailers.py"),
               "--task-file",    str(paths["task_file"]),
               "--status-file",  str(paths["crawl_status"])]
        if args.dry_run:  cmd.append("--dry-run")
        if args.limit:    cmd += ["--limit", str(args.limit)]
        if not run_step("STEP 1: crawl_trailers", cmd, log):
            log.error("크롤링 실패 — 중단"); return False

    # ── STEP 2: embed ────────────────────────────────────────────
    if start_idx <= 1:
        cmd = [PYTHON, str(SCRIPTS_DIR / "batch_embed.py"),
               "--output",             "parquet",
               "--out-file",           str(paths["parquet_out"]),
               "--crawl-status-file",  str(paths["crawl_status"]),
               "--embed-status-file",  str(paths["embed_status"]),
               "--delete-after-embed"]
        if not run_step("STEP 2: batch_embed", cmd, log):
            log.error("임베딩 실패 — 중단"); return False

        if not args.dry_run and not paths["parquet_out"].exists():
            log.error(f"parquet 없음: {paths['parquet_out']}"); return False

    return True


def run_ingest(parquet_files: list, args, log: logging.Logger):
    """적재 → 전파 → 정규화 (파티션 parquet 전부 처리)"""
    ingest = str(SCRIPTS_DIR / "ingest_to_db.py")

    for pq in parquet_files:
        if not Path(pq).exists():
            log.warning(f"parquet 없음, 건너뜀: {pq}"); continue
        cmd = [PYTHON, ingest, "--file", str(pq)]
        if args.dry_run: cmd.append("--dry-run")
        if not run_step(f"STEP 3-1: ingest ({Path(pq).name})", cmd, log):
            log.error("적재 실패"); return False

    cmd = [PYTHON, ingest, "--propagate"]
    if args.dry_run: cmd.append("--dry-run")
    run_step("STEP 3-2: propagate", cmd, log)

    cmd = [PYTHON, ingest, "--normalize"]
    if args.dry_run: cmd.append("--dry-run")
    run_step("STEP 3-3: normalize", cmd, log)

    return True


def main():
    parser = argparse.ArgumentParser(description="VOD 임베딩 파이프라인")
    parser.add_argument('--partition',        type=str, default='',
                        choices=['', 'P1', 'P2', 'P3'],
                        help='파티션 (P1/P2/P3). 미지정 시 tasks_missing.json 단일 실행')
    parser.add_argument('--task-file',        type=str, default='',
                        help='단일 실행 시 작업 파일 (기본: data/tasks_missing.json)')
    parser.add_argument('--start-from',       type=str, default='crawl',
                        choices=['crawl', 'embed', 'ingest'],
                        help='시작 단계 (기본: crawl)')
    parser.add_argument('--merge-partitions', action='store_true',
                        help='P1/P2/P3 parquet를 모두 모아 ingest만 실행')
    parser.add_argument('--dry-run',          action='store_true')
    parser.add_argument('--limit',            type=int, default=0)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── --merge-partitions: 모든 파티션 parquet → ingest ─────────
    if args.merge_partitions:
        log = setup_logger(DATA_DIR / "pipeline_merge.log")
        log.info("=== 파티션 병합 적재 시작 ===")
        parquets = [partition_paths(p)["parquet_out"] for p in ["P1", "P2", "P3"]]
        run_ingest(parquets, args, log)
        return

    # ── 파티션 or 단일 실행 ───────────────────────────────────────
    partition = args.partition
    paths     = partition_paths(partition)

    # 단일 실행 시 --task-file 우선
    if not partition and args.task_file:
        paths["task_file"] = Path(args.task_file)

    log = setup_logger(paths["pipeline_log"])
    log.info("=" * 60)
    log.info(f"파이프라인 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info(f"파티션={partition or '단일'} / 시작단계={args.start_from} / "
             f"task={paths['task_file'].name}")
    log.info("=" * 60)

    ok = run_partition(paths, args, log)

    # 파티션 단독 실행이면 ingest 포함
    if ok and args.start_from in ('crawl', 'embed', 'ingest'):
        if args.start_from == 'ingest' or (ok and args.start_from != 'ingest'):
            # crawl/embed 완료 후 자동으로 ingest 실행
            run_ingest([paths["parquet_out"]], args, log)

    log.info("=" * 60)
    log.info(f"파이프라인 종료: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
