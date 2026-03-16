"""
VOD 임베딩 파이프라인 (단일 / 파티션 단독 / 다중 파티션 병합 적재)

crawl_trailers → batch_embed → ingest_to_db (+ propagate)

실행 예시:
    # 단일 실행 (task-file 직접 지정)
    python scripts/run_pipeline.py --task-file data/tasks_new.json

    # 파티션 단독 실행 (파티션 이름 자유 지정)
    python scripts/run_pipeline.py --partition P1 --task-file data/tasks_P1.json
    python scripts/run_pipeline.py --partition A
    python scripts/run_pipeline.py --partition K1

    # 크롤 완료 후 임베딩부터 이어서
    python scripts/run_pipeline.py --partition P1 --start-from embed

    # 임베딩 완료 후 여러 파티션 parquet 한꺼번에 DB 적재
    python scripts/run_pipeline.py --start-from ingest --partitions P1,P2,P3

    # 동작 확인
    python scripts/run_pipeline.py --partition P1 --dry-run --limit 3

로그:
    data/pipeline_{partition}.log  (파티션 실행)
    data/pipeline.log              (단일 실행)
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


def partition_paths(partition: str, task_file: str = '') -> dict:
    """파티션별 파일 경로 딕셔너리.

    task_file이 명시된 경우 해당 파일명 stem을 기준으로 경로를 결정.
    그 외에는 파티션 이름(partition)을 suffix로 사용.
    """
    if task_file:
        stem = Path(task_file).stem          # e.g. "tasks_P1" → "tasks_P1"
        base = stem.removeprefix("tasks_") if stem.startswith("tasks_") else stem
        sfx  = f"_{base}"
        return {
            "task_file":    Path(task_file),
            "crawl_status": DATA_DIR / f"crawl_status{sfx}.json",
            "embed_status": DATA_DIR / f"embed_status{sfx}.json",
            "parquet_out":  DATA_DIR / f"embeddings{sfx}.parquet",
            "pipeline_log": DATA_DIR / f"pipeline{sfx}.log",
        }

    sfx = f"_{partition}" if partition else ""
    return {
        "task_file":    DATA_DIR / f"tasks{sfx}.json",
        "crawl_status": DATA_DIR / f"crawl_status{sfx}.json",
        "embed_status": DATA_DIR / f"embed_status{sfx}.json",
        "parquet_out":  DATA_DIR / f"embeddings{sfx}.parquet",
        "pipeline_log": DATA_DIR / f"pipeline{sfx}.log",
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


def run_crawl_embed(paths: dict, args, log: logging.Logger) -> bool:
    """crawl → embed 순서로 파티션 1개 처리"""
    stages    = ['crawl', 'embed', 'ingest']
    start_idx = stages.index(args.start_from)

    # ── STEP 1: crawl ────────────────────────────────────────────
    if start_idx <= 0:
        cmd = [PYTHON, str(SCRIPTS_DIR / "crawl_trailers.py"),
               "--task-file",   str(paths["task_file"]),
               "--status-file", str(paths["crawl_status"])]
        if args.dry_run: cmd.append("--dry-run")
        if args.limit:   cmd += ["--limit", str(args.limit)]
        if not run_step("STEP 1: crawl_trailers", cmd, log):
            log.error("크롤링 실패 — 중단"); return False

    # ── STEP 2: embed ────────────────────────────────────────────
    if start_idx <= 1:
        cmd = [PYTHON, str(SCRIPTS_DIR / "batch_embed.py"),
               "--output",            "parquet",
               "--out-file",          str(paths["parquet_out"]),
               "--crawl-status-file", str(paths["crawl_status"]),
               "--embed-status-file", str(paths["embed_status"]),
               "--delete-after-embed"]
        if not run_step("STEP 2: batch_embed", cmd, log):
            log.error("임베딩 실패 — 중단"); return False

        if not args.dry_run and not paths["parquet_out"].exists():
            log.warning(f"parquet 없음 (성공 건 0일 수 있음): {paths['parquet_out']}")

    return True


def run_ingest(parquet_files: list, args, log: logging.Logger) -> bool:
    """ingest → propagate (parquet 목록 전부 처리)"""
    ingest = str(SCRIPTS_DIR / "ingest_to_db.py")

    for pq in parquet_files:
        if not Path(pq).exists():
            log.warning(f"parquet 없음, 건너뜀: {pq}"); continue
        cmd = [PYTHON, ingest, "--file", str(pq)]
        if args.dry_run: cmd.append("--dry-run")
        if not run_step(f"STEP 3: ingest ({Path(pq).name})", cmd, log):
            log.error("적재 실패"); return False

    cmd = [PYTHON, ingest, "--propagate"]
    if args.dry_run: cmd.append("--dry-run")
    run_step("STEP 4: propagate", cmd, log)

    return True


def main():
    parser = argparse.ArgumentParser(description="VOD 임베딩 파이프라인")
    parser.add_argument('--partition',   type=str, default='',
                        help='파티션 레이블 (P1, A, K1 등 자유 지정). 미지정 시 단일 실행')
    parser.add_argument('--task-file',   type=str, default='',
                        help='작업 파일 경로. 미지정 시 data/tasks_{partition}.json 사용')
    parser.add_argument('--start-from',  type=str, default='crawl',
                        choices=['crawl', 'embed', 'ingest'],
                        help='시작 단계 (기본: crawl)')
    parser.add_argument('--partitions',  type=str, default='',
                        help='ingest 병합 시 대상 파티션 레이블 (쉼표 구분, 예: P1,P2,P3)')
    parser.add_argument('--dry-run',     action='store_true')
    parser.add_argument('--limit',       type=int, default=0)
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── --start-from ingest + --partitions: 여러 파티션 parquet 일괄 적재 ──
    if args.start_from == 'ingest' and args.partitions:
        labels = [p.strip() for p in args.partitions.split(',') if p.strip()]
        log = setup_logger(DATA_DIR / "pipeline_merge.log")
        log.info(f"=== 파티션 병합 적재 시작: {labels} ===")
        parquets = [partition_paths(p)["parquet_out"] for p in labels]
        run_ingest(parquets, args, log)
        return

    # ── 단일 또는 파티션 단독 실행 ──────────────────────────────────────
    paths = partition_paths(args.partition, args.task_file)
    log   = setup_logger(paths["pipeline_log"])

    log.info("=" * 60)
    log.info(f"파이프라인 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info(f"파티션={args.partition or '단일'} / 시작단계={args.start_from} / "
             f"task={paths['task_file'].name}")
    log.info("=" * 60)

    if args.start_from in ('crawl', 'embed'):
        ok = run_crawl_embed(paths, args, log)
        if not ok:
            return

    run_ingest([paths["parquet_out"]], args, log)

    log.info("=" * 60)
    log.info(f"파이프라인 종료: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
