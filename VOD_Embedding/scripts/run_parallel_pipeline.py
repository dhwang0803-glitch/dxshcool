"""
VOD 임베딩 병렬 파이프라인 마스터 스크립트

실행 흐름:
    1. task JSON을 N분할 → tasks_{label}_P{i}.json 생성
    2. crawl  : N개 프로세스 병렬 실행 (I/O bound)
    3. embed  : N개 파티션 순차 실행  (CPU/GPU bound — 동시 실행 시 OOM 위험)
    4. ingest : N개 parquet 병렬 DB 적재 (파티션별 vod_id 겹치지 않음)
    5. propagate: 1회 단독 실행 (시리즈 임베딩 전파)

실행 예시:
    python scripts/run_parallel_pipeline.py --task-file data/tasks_tmdb_new2025.json
    python scripts/run_parallel_pipeline.py --task-file data/tasks_tmdb_new2025.json --parts 4
    python scripts/run_parallel_pipeline.py --task-file data/tasks_tmdb_new2025.json --start-from embed
    python scripts/run_parallel_pipeline.py --task-file data/tasks_tmdb_new2025.json --start-from ingest
    python scripts/run_parallel_pipeline.py --task-file data/tasks_tmdb_new2025.json --dry-run --limit 3

로그:
    data/parallel_{label}.log          마스터 로그
    data/pipeline_{label}_P{i}.log     파티션별 상세 로그
"""

import sys
import os
import json
import math
import time
import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
SCRIPTS_DIR  = Path(__file__).parent
PYTHON       = sys.executable


# ── 유틸 ─────────────────────────────────────────────────────────────────────

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


def split_task_file(task_file: Path, label: str, parts: int) -> list[Path]:
    """task JSON을 parts 등분해 data/tasks_{label}_P{i}.json 생성. 생성된 경로 목록 반환."""
    with open(task_file, encoding='utf-8') as f:
        task = json.load(f)

    vods  = task.get('vods', [])
    total = len(vods)
    chunk = math.ceil(total / parts)
    paths = []

    for i in range(1, parts + 1):
        part_vods = vods[(i - 1) * chunk: i * chunk]
        part_task = {
            'team':        f"{label}_P{i}",
            'description': task.get('description', '') + f" (파티션 {i}/{parts})",
            'total':       len(part_vods),
            'created_at':  datetime.now().isoformat(),
            'vods':        part_vods,
        }
        out = DATA_DIR / f"tasks_{label}_P{i}.json"
        with open(out, 'w', encoding='utf-8') as f:
            json.dump(part_task, f, ensure_ascii=False, indent=2)
        paths.append(out)

    return paths


def partition_paths(label: str, part: int) -> dict:
    """파티션별 파일 경로 딕셔너리."""
    sfx = f"{label}_P{part}"
    return {
        "task_file":    DATA_DIR / f"tasks_{sfx}.json",
        "crawl_status": DATA_DIR / f"crawl_status_{sfx}.json",
        "embed_status": DATA_DIR / f"embed_status_{sfx}.json",
        "parquet_out":  DATA_DIR / f"embeddings_{sfx}.parquet",
        "pipeline_log": DATA_DIR / f"pipeline_{sfx}.log",
    }


# ── STEP 1: 병렬 크롤링 ──────────────────────────────────────────────────────

def run_parallel_crawl(label: str, parts: int, args, log: logging.Logger) -> bool:
    """crawl_trailers.py N개 병렬 실행. 모두 완료될 때까지 대기."""
    log.info("=" * 60)
    log.info(f"STEP 1: 크롤링 {parts}병렬 시작")
    log.info("=" * 60)

    procs, log_files = [], []
    for i in range(1, parts + 1):
        paths    = partition_paths(label, i)
        log_path = paths["pipeline_log"]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        lf  = open(log_path, 'w', encoding='utf-8')
        log_files.append(lf)

        cmd = [PYTHON, str(SCRIPTS_DIR / "crawl_trailers.py"),
               "--task-file",   str(paths["task_file"]),
               "--status-file", str(paths["crawl_status"])]
        if args.dry_run: cmd.append("--dry-run")
        if args.limit:   cmd += ["--limit", str(args.limit)]

        log.info(f"  파티션 P{i} crawl 시작 → {paths['task_file'].name}")
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT,
                             cwd=str(PROJECT_ROOT), env=os.environ.copy())
        procs.append((i, p))

    # 진행 모니터링 (30초 간격)
    log.info(f"  {parts}개 프로세스 실행 중...")
    while True:
        alive = [(i, p) for i, p in procs if p.poll() is None]
        if not alive:
            break
        parts_status = []
        for i in range(1, parts + 1):
            sf = partition_paths(label, i)["crawl_status"]
            if sf.exists():
                try:
                    d = json.loads(sf.read_text(encoding='utf-8'))
                    ok = d.get('success', 0); fail = d.get('failed', 0)
                    parts_status.append(f"P{i}:{ok}ok/{fail}fail")
                except Exception:
                    parts_status.append(f"P{i}:읽기실패")
            else:
                parts_status.append(f"P{i}:대기")
        log.info(f"  진행: {' | '.join(parts_status)} / 실행중 {len(alive)}개")
        time.sleep(30)

    for lf in log_files:
        lf.close()

    failed = [i for i, p in procs if p.returncode != 0]
    if failed:
        log.error(f"  크롤링 실패 파티션: {failed}")
        return False

    # 완료 통계
    total_ok = total_fail = 0
    for i in range(1, parts + 1):
        sf = partition_paths(label, i)["crawl_status"]
        if sf.exists():
            d = json.loads(sf.read_text(encoding='utf-8'))
            total_ok   += d.get('success', 0)
            total_fail += d.get('failed', 0)
    log.info(f"STEP 1 완료: 성공 {total_ok}건 / 실패 {total_fail}건")
    return True


# ── STEP 2: 순차 임베딩 ──────────────────────────────────────────────────────

def run_sequential_embed(label: str, parts: int, args, log: logging.Logger) -> list[Path]:
    """batch_embed.py N개 순차 실행. 생성된 parquet 경로 목록 반환."""
    log.info("=" * 60)
    log.info(f"STEP 2: 임베딩 순차 실행 ({parts}개 파티션)")
    log.info("=" * 60)

    parquets = []
    for i in range(1, parts + 1):
        paths = partition_paths(label, i)
        log.info(f"  파티션 P{i} 임베딩 시작...")
        start = datetime.now()

        # 파티션 로그에 append
        log_path = paths["pipeline_log"]
        with open(log_path, 'a', encoding='utf-8') as lf:
            cmd = [PYTHON, str(SCRIPTS_DIR / "batch_embed.py"),
                   "--output",            "parquet",
                   "--out-file",          str(paths["parquet_out"]),
                   "--crawl-status-file", str(paths["crawl_status"]),
                   "--embed-status-file", str(paths["embed_status"]),
                   "--delete-after-embed"]
            proc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                                  cwd=str(PROJECT_ROOT), env=os.environ.copy())

        elapsed = int((datetime.now() - start).total_seconds())
        if proc.returncode != 0:
            log.error(f"  P{i} 임베딩 실패 (exit={proc.returncode}) — 중단")
            return parquets  # 지금까지 성공한 것만 반환
        if paths["parquet_out"].exists():
            parquets.append(paths["parquet_out"])
            log.info(f"  P{i} 임베딩 완료 ({elapsed//60}분 {elapsed%60}초) → {paths['parquet_out'].name}")
        else:
            log.warning(f"  P{i} parquet 없음 (성공 건 0일 수 있음)")

    log.info(f"STEP 2 완료: parquet {len(parquets)}개 생성")
    return parquets


# ── STEP 3: 병렬 DB 적재 ─────────────────────────────────────────────────────

def run_parallel_ingest(parquets: list[Path], args, log: logging.Logger) -> bool:
    """ingest_to_db.py를 parquet 수만큼 병렬 실행. propagate는 단독 1회."""
    if not parquets:
        log.warning("적재할 parquet 없음 — ingest 건너뜀")
        return True

    log.info("=" * 60)
    log.info(f"STEP 3: DB 적재 {len(parquets)}병렬 시작")
    log.info("=" * 60)

    ingest_script = str(SCRIPTS_DIR / "ingest_to_db.py")
    procs, log_files = [], []

    for pq in parquets:
        if not pq.exists():
            log.warning(f"  parquet 없음, 건너뜀: {pq.name}")
            continue
        log_path = DATA_DIR / f"ingest_{pq.stem}.log"
        lf = open(log_path, 'w', encoding='utf-8')
        log_files.append(lf)

        cmd = [PYTHON, ingest_script, "--file", str(pq)]
        if args.dry_run: cmd.append("--dry-run")
        log.info(f"  ingest 시작: {pq.name}")
        p = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT,
                             cwd=str(PROJECT_ROOT), env=os.environ.copy())
        procs.append((pq.name, p))

    # 완료 대기
    while True:
        alive = [(nm, p) for nm, p in procs if p.poll() is None]
        if not alive:
            break
        log.info(f"  DB 적재 실행중 {len(alive)}개...")
        time.sleep(15)

    for lf in log_files:
        lf.close()

    failed = [nm for nm, p in procs if p.returncode != 0]
    if failed:
        log.error(f"  ingest 실패: {failed}")
        return False

    log.info(f"STEP 3 완료: {len(procs)}개 parquet 적재")

    # propagate — 단독 1회
    log.info("=" * 60)
    log.info("STEP 4: propagate (시리즈 임베딩 전파)")
    log.info("=" * 60)
    cmd = [PYTHON, ingest_script, "--propagate"]
    if args.dry_run: cmd.append("--dry-run")
    proc = subprocess.run(cmd, encoding='utf-8', errors='replace',
                          cwd=str(PROJECT_ROOT), env=os.environ.copy())
    if proc.returncode == 0:
        log.info("STEP 4 propagate 완료")
    else:
        log.error("STEP 4 propagate 실패")
    return True


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VOD 임베딩 병렬 파이프라인")
    parser.add_argument('--task-file',   required=True,
                        help='작업 JSON 파일 (예: data/tasks_tmdb_new2025.json)')
    parser.add_argument('--parts',       type=int, default=4,
                        help='분할 수 (기본: 4)')
    parser.add_argument('--start-from',  type=str, default='crawl',
                        choices=['crawl', 'embed', 'ingest'],
                        help='시작 단계 (기본: crawl)')
    parser.add_argument('--dry-run',     action='store_true')
    parser.add_argument('--limit',       type=int, default=0,
                        help='파티션당 처리 건수 제한 (테스트용)')
    args = parser.parse_args()

    task_file = Path(args.task_file)
    if not task_file.exists():
        print(f"[ERROR] task 파일 없음: {task_file}", file=sys.stderr)
        sys.exit(1)

    # label: "tasks_" 제거한 stem (예: tasks_tmdb_new2025 → tmdb_new2025)
    stem  = task_file.stem
    label = stem.removeprefix("tasks_") if stem.startswith("tasks_") else stem

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = setup_logger(DATA_DIR / f"parallel_{label}.log")

    log.info("=" * 60)
    log.info(f"병렬 파이프라인 시작: {datetime.now():%Y-%m-%d %H:%M:%S}")
    log.info(f"task={task_file.name} / parts={args.parts} / start={args.start_from}"
             + (" / DRY-RUN" if args.dry_run else ""))
    log.info("=" * 60)
    t_start = datetime.now()

    stages = ['crawl', 'embed', 'ingest']
    start_idx = stages.index(args.start_from)

    # ── task 분할 (crawl/embed 시작 시) ──
    if start_idx <= 1:
        log.info(f"task 파일 {args.parts}분할 중...")
        split_task_file(task_file, label, args.parts)
        log.info(f"  → data/tasks_{label}_P1~P{args.parts}.json 생성")

    # ── STEP 1: 병렬 크롤링 ──
    if start_idx <= 0:
        ok = run_parallel_crawl(label, args.parts, args, log)
        if not ok:
            log.error("크롤링 단계 실패 — 파이프라인 중단")
            sys.exit(1)

    # ── STEP 2: 순차 임베딩 ──
    if start_idx <= 1:
        parquets = run_sequential_embed(label, args.parts, args, log)
        if not parquets and not args.dry_run:
            log.error("임베딩 단계 실패 또는 결과 없음 — 파이프라인 중단")
            sys.exit(1)
    else:
        # --start-from ingest: 기존 parquet 파일 직접 참조
        parquets = []
        for i in range(1, args.parts + 1):
            pq = partition_paths(label, i)["parquet_out"]
            if pq.exists():
                parquets.append(pq)
                log.info(f"  기존 parquet 사용: {pq.name}")
            else:
                log.warning(f"  parquet 없음 (건너뜀): {pq.name}")

    # ── STEP 3: 병렬 ingest + propagate ──
    run_parallel_ingest(parquets, args, log)

    elapsed = int((datetime.now() - t_start).total_seconds())
    log.info("=" * 60)
    log.info(f"파이프라인 종료: {datetime.now():%Y-%m-%d %H:%M:%S} "
             f"(총 {elapsed//60}분 {elapsed%60}초)")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
