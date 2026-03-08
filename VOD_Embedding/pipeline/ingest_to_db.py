"""
PLAN_03: pgvector DB 적재
data/video_embs_batch_*.pkl → vod_embedding 테이블

실행:
    conda activate myenv
    python pipeline/ingest_to_db.py
    python pipeline/ingest_to_db.py --dry-run
    python pipeline/ingest_to_db.py --batch data/video_embs_batch_001.pkl
    python pipeline/ingest_to_db.py --verify
"""

import sys
import os
import json
import pickle
import argparse
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"

COMMIT_INTERVAL = 1000   # N건마다 COMMIT
MODEL_NAME      = "clip-ViT-B-32"

INSERT_SQL = """
INSERT INTO vod_embedding (vod_id_fk, embedding, model_name, vector_magnitude)
VALUES (%(vod_id)s, %(embedding)s::vector, %(model_name)s, %(magnitude)s)
ON CONFLICT (vod_id_fk, model_name)
DO UPDATE SET
    embedding        = EXCLUDED.embedding,
    vector_magnitude = EXCLUDED.vector_magnitude,
    updated_at       = NOW()
"""

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "ingest.log", encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)


def load_env():
    env_path = PROJECT_ROOT.parent / "Database_Design" / ".env"
    if not env_path.exists():
        env_path = PROJECT_ROOT.parent / ".env"
    env = {}
    if env_path.exists():
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env


def get_db_conn():
    env = load_env()
    import psycopg2
    conn = psycopg2.connect(
        host=env.get('DB_HOST', 'localhost'),
        port=int(env.get('DB_PORT', 5432)),
        dbname=env.get('DB_NAME', 'postgres'),
        user=env.get('DB_USER', 'postgres'),
        password=env.get('DB_PASSWORD', ''),
    )
    conn.autocommit = False
    return conn


def to_pgvector_str(vec: np.ndarray) -> str:
    """numpy float32 → '[f1,f2,...,f512]' 문자열 (pgvector 형식)"""
    return '[' + ','.join(f'{x:.8f}' for x in vec) + ']'


def check_pgvector(conn) -> bool:
    """pgvector 확장 설치 여부 확인"""
    cur = conn.cursor()
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    row = cur.fetchone()
    if row:
        log.info(f"pgvector {row[0]} 확인됨")
        return True
    else:
        log.error("pgvector 미설치 — CREATE EXTENSION IF NOT EXISTS vector 실행 필요")
        return False


def check_table_exists(conn) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT to_regclass('public.vod_embedding') IS NOT NULL"
    )
    exists = cur.fetchone()[0]
    if not exists:
        log.error("vod_embedding 테이블 없음 — Database_Design/schema/create_embedding_tables.sql 실행 필요")
    return exists


def get_batch_files(data_dir: Path, specific_file: str = None) -> list:
    if specific_file:
        p = Path(specific_file)
        if not p.is_absolute():
            p = data_dir / specific_file
        return [p] if p.exists() else []
    return sorted(data_dir.glob("video_embs_batch_*.pkl"))


def ingest_batch_file(conn, pkl_path: Path, dry_run: bool) -> tuple:
    """
    pkl 파일 하나를 DB에 적재.
    반환: (inserted, skipped, errors)
    """
    with open(pkl_path, 'rb') as f:
        batch = pickle.load(f)

    inserted = 0
    skipped  = 0
    errors   = 0
    cur      = conn.cursor()

    for i, item in enumerate(batch):
        vod_id = item.get("vod_id")
        vec    = item.get("vector")

        if vec is None or not isinstance(vec, np.ndarray):
            log.warning(f"벡터 없음: {vod_id}")
            skipped += 1
            continue

        if vec.shape != (512,):
            log.warning(f"벡터 차원 불일치 {vec.shape}: {vod_id}")
            skipped += 1
            continue

        params = {
            "vod_id":     vod_id,
            "embedding":  to_pgvector_str(vec),
            "model_name": MODEL_NAME,
            "magnitude":  float(np.linalg.norm(vec)),
        }

        if dry_run:
            inserted += 1
            continue

        try:
            cur.execute(INSERT_SQL, params)
            inserted += 1
        except Exception as e:
            log.error(f"INSERT 실패 {vod_id}: {e}")
            conn.rollback()
            errors += 1
            continue

        if (i + 1) % COMMIT_INTERVAL == 0:
            conn.commit()
            log.info(f"  COMMIT ({i+1}/{len(batch)})")

    if not dry_run:
        conn.commit()

    return inserted, skipped, errors


def run_verify(conn):
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM vod_embedding")
    embedded = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM vod")
    total_vod = cur.fetchone()[0]

    coverage = round(embedded / total_vod * 100, 1) if total_vod > 0 else 0.0

    cur.execute("SELECT COUNT(*) FROM vod_embedding WHERE vector_magnitude < 0.01 OR vector_magnitude > 100")
    anomalies = cur.fetchone()[0]

    cur.execute("SELECT model_name, COUNT(*) FROM vod_embedding GROUP BY model_name ORDER BY COUNT(*) DESC")
    models = cur.fetchall()

    print("\n=== 적재 검증 결과 ===")
    print(f"  vod_embedding 건수: {embedded:,}개")
    print(f"  vod 테이블 전체:    {total_vod:,}개")
    print(f"  커버리지:           {coverage}%")
    print(f"  이상 벡터:          {anomalies}개")
    print(f"  모델별 분포:")
    for model, cnt in models:
        print(f"    {model}: {cnt:,}개")
    print()

    if coverage < 70.0:
        log.warning(f"커버리지 {coverage}% < 목표 70%")
    else:
        log.info(f"커버리지 목표 달성: {coverage}%")


def create_index_after_ingest(conn):
    """전체 적재 완료 후 IVF_FLAT 인덱스 생성"""
    log.info("IVF_FLAT 인덱스 생성 중... (수 분 소요)")
    cur = conn.cursor()
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_vod_emb_ivfflat ON vod_embedding
            USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)
    conn.commit()
    log.info("인덱스 생성 완료")


def main():
    parser = argparse.ArgumentParser(description="pgvector DB 적재")
    parser.add_argument('--batch',   type=str, default='', help='특정 pkl 파일만 적재')
    parser.add_argument('--dry-run', action='store_true', help='DB INSERT 없이 확인만')
    parser.add_argument('--verify',  action='store_true', help='적재 결과 검증만')
    parser.add_argument('--create-index', action='store_true', help='적재 후 IVF_FLAT 인덱스 생성')
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_db_conn()
    try:
        if args.verify:
            run_verify(conn)
            return

        if not check_pgvector(conn):
            sys.exit(1)
        if not check_table_exists(conn):
            sys.exit(1)

        batch_files = get_batch_files(DATA_DIR, args.batch)
        if not batch_files:
            log.error("적재할 pkl 파일 없음 — PLAN_02 (batch_embed.py) 먼저 실행")
            sys.exit(1)

        log.info(f"적재 대상 배치 파일: {len(batch_files)}개")
        if args.dry_run:
            log.info("[DRY-RUN] 실제 INSERT 없음")

        total_inserted = 0
        total_skipped  = 0
        total_errors   = 0

        for pkl_path in batch_files:
            log.info(f"처리 중: {pkl_path.name}")
            ins, skip, err = ingest_batch_file(conn, pkl_path, args.dry_run)
            total_inserted += ins
            total_skipped  += skip
            total_errors   += err
            log.info(f"  → 삽입:{ins}  스킵:{skip}  오류:{err}")

        log.info(f"전체 완료 — 삽입:{total_inserted:,}  스킵:{total_skipped}  오류:{total_errors}")

        if args.create_index and not args.dry_run:
            create_index_after_ingest(conn)

        run_verify(conn)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
