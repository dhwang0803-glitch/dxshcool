"""
PLAN_03: pgvector DB 적재
data/video_embs_batch_*.pkl → vod_embedding 테이블

실행:
    conda activate myenv
    python pipeline/ingest_to_db.py                  # 대표 에피소드 적재
    python pipeline/ingest_to_db.py --dry-run
    python pipeline/ingest_to_db.py --batch data/video_embs_batch_001.pkl
    python pipeline/ingest_to_db.py --verify
    python pipeline/ingest_to_db.py --propagate      # 시리즈 전체 vod_id에 임베딩 복사

    # 팀원이 제출한 parquet → DB 적재 (L2 정규화 자동 적용)
    python pipeline/ingest_to_db.py --from-parquet data/embeddings_홍길동.parquet
    python pipeline/ingest_to_db.py --from-parquet data/embeddings_홍길동.parquet --dry-run

전략:
    시리즈 단위 ct_cl (TV드라마/TV애니메이션/키즈/TV시사교양/영화):
        대표 에피소드 1개 적재 후 --propagate로 같은 series_nm 전체에 복사
    에피소드 단위 ct_cl (TV 연예/오락):
        각 에피소드 개별 적재, 전파 없음
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
import pandas as pd
from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"

COMMIT_INTERVAL  = 1000         # N건마다 COMMIT
MODEL_VERSION    = "clip-ViT-B-32"
EMBEDDING_TYPE   = "CLIP"       # CLIP / CONTENT / HYBRID
EMBEDDING_DIM    = 512
FRAME_COUNT      = 10           # batch_embed.py N_FRAMES와 동일
SOURCE_TYPE      = "TRAILER"    # TRAILER / FULL

# 에피소드 단위 임베딩 ct_cl — 시리즈 전파 제외
EPISODE_EMBED_CT_CL = {'TV 연예/오락'}

# ON CONFLICT 기준: vod_id_fk UNIQUE (Database_Design 스키마 기준)
INSERT_SQL = """
INSERT INTO vod_embedding (
    vod_id_fk, embedding,
    embedding_type, embedding_dim, model_version,
    vector_magnitude, frame_count, source_type
)
VALUES (
    %(vod_id)s, %(embedding)s::vector,
    %(embedding_type)s, %(embedding_dim)s, %(model_version)s,
    %(magnitude)s, %(frame_count)s, %(source_type)s
)
ON CONFLICT (vod_id_fk)
DO UPDATE SET
    embedding        = EXCLUDED.embedding,
    embedding_type   = EXCLUDED.embedding_type,
    model_version    = EXCLUDED.model_version,
    vector_magnitude = EXCLUDED.vector_magnitude,
    frame_count      = EXCLUDED.frame_count,
    source_type      = EXCLUDED.source_type,
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


def get_db_conn():
    load_dotenv()
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
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


# Database_Design/schema/create_embedding_tables.sql 과 동일한 스키마
# VPC에서는 create_embedding_tables.sql로 생성. 로컬 개발 시에만 여기서 자동 생성.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vod_embedding (
    vod_embedding_id    BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL UNIQUE,
    embedding           VECTOR(512)     NOT NULL,
    embedding_type      VARCHAR(32)     NOT NULL DEFAULT 'CLIP',
    embedding_dim       INTEGER         NOT NULL DEFAULT 512,
    model_version       VARCHAR(64)     NOT NULL DEFAULT 'clip-ViT-B-32',
    vector_magnitude    REAL,
    frame_count         SMALLINT,
    source_type         VARCHAR(32)     NOT NULL DEFAULT 'TRAILER',
    source_url          TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW(),
    CONSTRAINT chk_embedding_type CHECK (embedding_type IN ('CLIP', 'CONTENT', 'HYBRID')),
    CONSTRAINT chk_source_type    CHECK (source_type IN ('TRAILER', 'FULL')),
    CONSTRAINT chk_embedding_dim  CHECK (embedding_dim > 0)
);
"""

def ensure_table(conn):
    """vod_embedding 테이블 없으면 자동 생성"""
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.vod_embedding')")
    if cur.fetchone()[0] is None:
        log.info("vod_embedding 테이블 생성 중...")
        cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        log.info("테이블 생성 완료")
    else:
        log.info("vod_embedding 테이블 확인됨")


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
            "vod_id":          vod_id,
            "embedding":       to_pgvector_str(vec),
            "embedding_type":  EMBEDDING_TYPE,
            "embedding_dim":   EMBEDDING_DIM,
            "model_version":   MODEL_VERSION,
            "magnitude":       float(np.linalg.norm(vec)),
            "frame_count":     FRAME_COUNT,
            "source_type":     SOURCE_TYPE,
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


def propagate_series_embeddings(conn, crawl_status_path: Path, dry_run: bool = False) -> int:
    """
    crawl_status.json 기반으로 시리즈 대표 vod_id의 임베딩을
    같은 series_nm 내 전체 vod_id에 SQL 수준으로 복사.

    - EPISODE_EMBED_CT_CL(TV 연예/오락): 건너뜀
    - series_nm 없는 항목: 건너뜀
    - 대표 vod_id가 vod_embedding에 없는 항목: 건너뜀
    """
    with open(crawl_status_path, encoding='utf-8') as f:
        crawl_data = json.load(f)
    crawl_vods = crawl_data.get("vods", {})

    cur = conn.cursor()
    total_propagated = 0
    total_skipped    = 0

    for rep_vod_id, info in crawl_vods.items():
        if info.get("status") != "success":
            continue

        ct_cl          = info.get("ct_cl")
        series_nm      = info.get("series_nm")
        series_key     = info.get("series_key") or series_nm
        is_bad         = info.get("series_nm_is_bad", False)

        if ct_cl in EPISODE_EMBED_CT_CL or not series_key:
            continue

        # 대표 vod_id가 vod_embedding에 있는지 확인
        cur.execute("SELECT 1 FROM vod_embedding WHERE vod_id_fk = %s", (rep_vod_id,))
        if not cur.fetchone():
            total_skipped += 1
            continue

        # 같은 시리즈의 나머지 vod_id 조회
        # series_nm이 오염된 경우(is_bad): asset_nm LIKE '{series_key}%' 패턴으로 매칭
        # 정상인 경우: series_nm exact match
        if is_bad:
            cur.execute(
                "SELECT full_asset_id FROM vod "
                "WHERE ct_cl = %s AND asset_nm LIKE %s AND full_asset_id != %s",
                (ct_cl, series_key + '%', rep_vod_id)
            )
        else:
            cur.execute(
                "SELECT full_asset_id FROM vod "
                "WHERE series_nm = %s AND ct_cl = %s AND full_asset_id != %s",
                (series_nm, ct_cl, rep_vod_id)
            )
        siblings = [r[0] for r in cur.fetchall()]
        if not siblings:
            continue

        if dry_run:
            log.info(f"[DRY-RUN] {series_nm}: {len(siblings)}개 vod_id에 전파 예정")
            total_propagated += len(siblings)
            continue

        # 대표의 임베딩을 형제 vod_id들에 SQL로 복사 (벡터 재인코딩 없이)
        for sib_id in siblings:
            try:
                cur.execute("""
                    INSERT INTO vod_embedding (
                        vod_id_fk, embedding, embedding_type, embedding_dim,
                        model_version, vector_magnitude, frame_count, source_type
                    )
                    SELECT %s, embedding, embedding_type, embedding_dim,
                           model_version, vector_magnitude, frame_count, source_type
                    FROM vod_embedding
                    WHERE vod_id_fk = %s
                    ON CONFLICT (vod_id_fk) DO UPDATE SET
                        embedding        = EXCLUDED.embedding,
                        updated_at       = NOW()
                """, (sib_id, rep_vod_id))
                total_propagated += 1
            except Exception as e:
                log.warning(f"전파 실패 {sib_id}: {e}")
                conn.rollback()

        if total_propagated % COMMIT_INTERVAL == 0:
            conn.commit()

    if not dry_run:
        conn.commit()

    log.info(f"시리즈 전파 완료: {total_propagated:,}건 전파, {total_skipped}건 스킵(미적재)")
    return total_propagated


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


def ingest_parquet_file(conn, parquet_path: str, dry_run: bool) -> tuple:
    """
    팀원 제출 parquet (batch_embed.py --output parquet 산출물) → vod_embedding 적재.
    컬럼: vod_id (str), embedding (list[float32], 512차원)

    L2 정규화: batch_embed.py는 비정규화 벡터를 저장하므로
    vod_meta_embedding(magnitude=1.0)과 스케일 통일을 위해 적재 시 자동 정규화.
    """
    p = Path(parquet_path)
    if not p.exists():
        log.error(f"파일 없음: {p}")
        sys.exit(1)

    log.info(f"Parquet 로드: {p}")
    df = pd.read_parquet(p)

    # 컬럼 검증
    required = {"vod_id", "embedding"}
    missing = required - set(df.columns)
    if missing:
        log.error(f"필수 컬럼 없음: {missing}")
        sys.exit(1)

    log.info(f"  {len(df):,}건 로드 완료")
    if dry_run:
        log.info("[DRY-RUN] 실제 INSERT 없음")

    inserted = 0
    skipped  = 0
    errors   = 0
    cur      = conn.cursor()

    for i, row in enumerate(df.itertuples(index=False)):
        vod_id = row.vod_id
        vec    = np.array(row.embedding, dtype=np.float32)

        if vec.shape != (512,):
            log.warning(f"벡터 차원 불일치 {vec.shape}: {vod_id}")
            skipped += 1
            continue

        # L2 정규화 (비정규화 벡터를 magnitude=1.0으로 통일)
        norm = float(np.linalg.norm(vec))
        if norm < 1e-6:
            log.warning(f"영벡터 스킵: {vod_id}")
            skipped += 1
            continue
        vec = vec / norm

        params = {
            "vod_id":         vod_id,
            "embedding":      to_pgvector_str(vec),
            "embedding_type": EMBEDDING_TYPE,
            "embedding_dim":  EMBEDDING_DIM,
            "model_version":  MODEL_VERSION,
            "magnitude":      1.0,
            "frame_count":    FRAME_COUNT,
            "source_type":    SOURCE_TYPE,
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
            log.info(f"  COMMIT ({i+1:,}/{len(df):,})")

    if not dry_run:
        conn.commit()

    return inserted, skipped, errors


def main():
    parser = argparse.ArgumentParser(description="pgvector DB 적재")
    parser.add_argument('--batch',        type=str, default='', help='특정 pkl 파일만 적재')
    parser.add_argument('--dry-run',      action='store_true', help='DB INSERT 없이 확인만')
    parser.add_argument('--verify',       action='store_true', help='적재 결과 검증만')
    parser.add_argument('--create-index', action='store_true', help='적재 후 IVF_FLAT 인덱스 생성')
    parser.add_argument('--propagate',    action='store_true',
                        help='시리즈 대표 임베딩을 같은 series_nm 전체 vod_id에 복사 '
                             '(대표 적재 완료 후 실행)')
    parser.add_argument('--from-parquet', type=str, default='', metavar='PARQUET_PATH',
                        help='팀원 제출 parquet → vod_embedding 적재 (L2 정규화 자동 적용)')
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    conn = get_db_conn()
    try:
        if args.verify:
            run_verify(conn)
            return

        if not check_pgvector(conn):
            sys.exit(1)
        ensure_table(conn)

        # --from-parquet: 팀원 제출 parquet 적재 (L2 정규화 자동 적용)
        if args.from_parquet:
            log.info("=== parquet → vod_embedding 적재 시작 (L2 정규화 적용) ===")
            if args.dry_run:
                log.info("[DRY-RUN] 실제 INSERT 없음")
            ins, skip, err = ingest_parquet_file(conn, args.from_parquet, args.dry_run)
            log.info(f"완료 — 삽입:{ins:,}  스킵:{skip}  오류:{err}")
            run_verify(conn)
            return

        # --propagate: 시리즈 전파만 실행
        if args.propagate:
            crawl_status_path = DATA_DIR / "crawl_status.json"
            if not crawl_status_path.exists():
                log.error("crawl_status.json 없음 — PLAN_01 (crawl_trailers.py) 먼저 실행")
                sys.exit(1)
            log.info("=== 시리즈 임베딩 전파 시작 ===")
            if args.dry_run:
                log.info("[DRY-RUN] 실제 INSERT 없음")
            propagated = propagate_series_embeddings(conn, crawl_status_path, args.dry_run)
            log.info(f"전파 완료: {propagated:,}건")
            run_verify(conn)
            return

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
