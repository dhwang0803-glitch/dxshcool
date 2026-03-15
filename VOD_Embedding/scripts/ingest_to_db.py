"""
PLAN_03: pgvector DB 적재
data/embeddings_*.parquet → vod_embedding 테이블

실행:
    conda activate myenv
    python scripts/ingest_to_db.py                                      # data/ 내 전체 parquet 적재
    python scripts/ingest_to_db.py --dry-run
    python scripts/ingest_to_db.py --file data/embeddings_아름_v2.parquet  # 특정 파일 적재
    python scripts/ingest_to_db.py --verify
    python scripts/ingest_to_db.py --propagate                          # 시리즈 전체 vod_id에 임베딩 복사

    # 팀원이 제출한 parquet → DB 적재 (L2 정규화 자동 적용)
    python scripts/ingest_to_db.py --from-parquet data/embeddings_홍길동.parquet
    python scripts/ingest_to_db.py --from-parquet data/embeddings_홍길동.parquet --dry-run

전략:
    시리즈 단위 ct_cl (TV드라마/TV애니메이션/키즈/TV시사교양/영화):
        대표 에피소드 1개 적재 후 --propagate로 같은 series_nm 전체에 복사
    에피소드 단위 ct_cl (TV 연예/오락):
        각 에피소드 개별 적재, 전파 없음

parquet 필수 컬럼:
    vod_id     : VOD 식별자 (vod.full_asset_id FK)
    embedding  : numpy.ndarray (512-dim, float32/float64)
"""

import sys
import os
import json
import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"

COMMIT_INTERVAL = 1000          # N건마다 COMMIT
MODEL_VERSION   = "clip-ViT-B-32"
EMBEDDING_TYPE  = "CLIP"        # DB 스키마 CHECK: ('CLIP', 'CONTENT', 'HYBRID')
EMBEDDING_DIM   = 512
FRAME_COUNT     = 10            # batch_embed.py N_FRAMES와 동일
SOURCE_TYPE     = "TRAILER"     # TRAILER / FULL

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
        host=env.get('DB_HOST'),
        port=int(env.get('DB_PORT', 5432)),
        dbname=env.get('DB_NAME'),
        user=env.get('DB_USER'),
        password=env.get('DB_PASSWORD'),
    )
    conn.autocommit = False
    return conn


def to_pgvector_str(vec: np.ndarray) -> str:
    """numpy array → '[f1,f2,...,f512]' 문자열 (pgvector 형식)"""
    return '[' + ','.join(f'{x:.8f}' for x in vec.astype(np.float32)) + ']'


def check_pgvector(conn) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    row = cur.fetchone()
    if row:
        log.info(f"pgvector {row[0]} 확인됨")
        return True
    log.error("pgvector 미설치 — CREATE EXTENSION IF NOT EXISTS vector 실행 필요")
    return False


# Database_Design/schemas/create_embedding_tables.sql 과 동일한 스키마
# VPC에서는 create_embedding_tables.sql로 생성. 로컬 개발 시에만 여기서 자동 생성.
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS vod_embedding (
    vod_embedding_id    BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL,
    embedding           VECTOR(512)     NOT NULL,
    embedding_type      VARCHAR(32)     NOT NULL DEFAULT 'CLIP',
    embedding_dim       INTEGER         NOT NULL DEFAULT 512,
    model_version       VARCHAR(64)     NOT NULL DEFAULT 'clip-ViT-B-32',
    frame_count         SMALLINT,
    source_type         VARCHAR(32)     NOT NULL DEFAULT 'TRAILER',
    source_url          TEXT,
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vod_embedding   UNIQUE (vod_id_fk),
    CONSTRAINT chk_embedding_type CHECK (embedding_type IN ('CLIP', 'CONTENT', 'HYBRID')),
    CONSTRAINT chk_source_type    CHECK (source_type IN ('TRAILER', 'FULL')),
    CONSTRAINT chk_embedding_dim  CHECK (embedding_dim > 0)
);
CREATE INDEX IF NOT EXISTS idx_vod_emb_type    ON vod_embedding (embedding_type);
CREATE INDEX IF NOT EXISTS idx_vod_emb_updated ON vod_embedding (updated_at DESC);
"""


def ensure_table(conn):
    cur = conn.cursor()
    cur.execute("SELECT to_regclass('public.vod_embedding')")
    if cur.fetchone()[0] is None:
        log.info("vod_embedding 테이블 생성 중...")
        cur.execute(CREATE_TABLE_SQL)
        conn.commit()
        log.info("테이블 생성 완료")
    else:
        log.info("vod_embedding 테이블 확인됨")


def get_parquet_files(data_dir: Path, specific_file: str = None) -> list:
    if specific_file:
        p = Path(specific_file)
        if not p.is_absolute():
            p = data_dir / specific_file
        return [p] if p.exists() else []
    return sorted(data_dir.glob("embeddings_*.parquet"))


def ingest_parquet_file(conn, parquet_path: Path, dry_run: bool) -> tuple:
    """
    parquet 파일을 읽어 vod_embedding 테이블에 적재.
    필수 컬럼: vod_id, embedding (512-dim)
    반환: (inserted, skipped, errors)
    """
    df = pd.read_parquet(parquet_path)

    required = {'vod_id', 'embedding'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"parquet 필수 컬럼 누락: {missing}")

    log.info(f"  parquet 로드: {len(df):,}행, 컬럼={df.columns.tolist()}")

    inserted = 0
    skipped  = 0
    errors   = 0
    cur      = conn.cursor()

    for i, row in enumerate(df.itertuples(index=False)):
        vod_id = row.vod_id
        vec    = np.array(row.embedding)

        if vec.shape != (512,):
            log.warning(f"벡터 차원 불일치 {vec.shape}: {vod_id}")
            skipped += 1
            continue

        # L2 정규화 (DB 적재 직전)
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm

        params = {
            "vod_id":         vod_id,
            "embedding":      to_pgvector_str(vec),
            "embedding_type": EMBEDDING_TYPE,
            "embedding_dim":  EMBEDDING_DIM,
            "model_version":  MODEL_VERSION,
            "magnitude":      float(np.linalg.norm(vec)),
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
            log.info(f"  COMMIT ({i+1}/{len(df)})")

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

    cur.execute("SELECT embedding_type, COUNT(*) FROM vod_embedding GROUP BY embedding_type ORDER BY COUNT(*) DESC")
    types = cur.fetchall()

    print("\n=== 적재 검증 결과 ===")
    print(f"  vod_embedding 건수: {embedded:,}개")
    print(f"  vod 테이블 전체:    {total_vod:,}개")
    print(f"  커버리지:           {coverage}%")
    print(f"  이상 벡터:          {anomalies}개")
    print(f"  타입별 분포:")
    for etype, cnt in types:
        print(f"    {etype}: {cnt:,}개")
    print()

    if coverage < 70.0:
        log.warning(f"커버리지 {coverage}% < 목표 70%")
    else:
        log.info(f"커버리지 목표 달성: {coverage}%")


def propagate_series_embeddings(conn, dry_run: bool = False) -> int:
    """
    vod 테이블 기반으로 시리즈 대표 vod_id의 임베딩을
    같은 (series_nm, ct_cl) 내 미적재 vod_id 전체에 SQL로 복사.

    전략:
    - TV 연예/오락: 에피소드별 개별 임베딩 → 전파 제외
    - 그 외 ct_cl: series_nm 동일 = 동일 콘텐츠 → 대표 임베딩 복사
    - series_nm이 NULL인 vod: 전파 불가 → 제외
    - 이미 vod_embedding에 있는 vod_id: ON CONFLICT DO NOTHING으로 건너뜀
    """
    cur = conn.cursor()

    # 전파 대상 건수 미리 확인
    excluded = ', '.join(f"'{c}'" for c in EPISODE_EMBED_CT_CL)
    cur.execute(f"""
        SELECT COUNT(DISTINCT v_target.full_asset_id)
        FROM vod v_target
        JOIN vod v_src
          ON v_src.series_nm = v_target.series_nm
         AND v_src.ct_cl     = v_target.ct_cl
        JOIN vod_embedding ve_src ON ve_src.vod_id_fk = v_src.full_asset_id
        WHERE v_target.ct_cl NOT IN ({excluded})
          AND v_target.series_nm IS NOT NULL
          AND v_src.full_asset_id != v_target.full_asset_id
          AND NOT EXISTS (
              SELECT 1 FROM vod_embedding ve_chk
              WHERE ve_chk.vod_id_fk = v_target.full_asset_id
          )
    """)
    target_count = cur.fetchone()[0]
    log.info(f"전파 대상: {target_count:,}건")

    if dry_run:
        log.info("[DRY-RUN] 실제 INSERT 없음")
        return target_count

    if target_count == 0:
        log.info("전파 대상 없음")
        return 0

    # 시리즈별로 대표 1건 선택(MIN vod_id_fk) 후 전체 미적재 형제에 복사
    cur.execute(f"""
        INSERT INTO vod_embedding (
            vod_id_fk, embedding, embedding_type, embedding_dim,
            model_version, vector_magnitude, frame_count, source_type
        )
        SELECT DISTINCT ON (v_target.full_asset_id)
            v_target.full_asset_id,
            ve_src.embedding,
            ve_src.embedding_type,
            ve_src.embedding_dim,
            ve_src.model_version,
            ve_src.vector_magnitude,
            ve_src.frame_count,
            ve_src.source_type
        FROM vod v_target
        JOIN vod v_src
          ON v_src.series_nm = v_target.series_nm
         AND v_src.ct_cl     = v_target.ct_cl
        JOIN vod_embedding ve_src ON ve_src.vod_id_fk = v_src.full_asset_id
        WHERE v_target.ct_cl NOT IN ({excluded})
          AND v_target.series_nm IS NOT NULL
          AND v_src.full_asset_id != v_target.full_asset_id
          AND NOT EXISTS (
              SELECT 1 FROM vod_embedding ve_chk
              WHERE ve_chk.vod_id_fk = v_target.full_asset_id
          )
        ORDER BY v_target.full_asset_id, v_src.full_asset_id
        ON CONFLICT (vod_id_fk) DO NOTHING
    """)
    propagated = cur.rowcount
    conn.commit()

    log.info(f"시리즈 전파 완료: {propagated:,}건")
    return propagated


def normalize_embeddings(conn, dry_run: bool = False) -> int:
    """
    vector_magnitude가 1.0이 아닌 벡터를 L2 정규화 후 DB UPDATE.
    정규화 기준: |magnitude - 1.0| > 0.001
    배치(FETCH_SIZE)로 처리하여 메모리 절약.
    """
    FETCH_SIZE = 500
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM vod_embedding
        WHERE vector_magnitude IS NULL
           OR vector_magnitude < 0.999
           OR vector_magnitude > 1.001
    """)
    total = cur.fetchone()[0]
    log.info(f"정규화 대상: {total:,}건")

    if dry_run:
        log.info("[DRY-RUN] 실제 UPDATE 없음")
        return total

    if total == 0:
        log.info("정규화 대상 없음 — 모든 벡터가 이미 L2 정규화 완료")
        return 0

    cur.execute("""
        SELECT vod_embedding_id, embedding
        FROM vod_embedding
        WHERE vector_magnitude IS NULL
           OR vector_magnitude < 0.999
           OR vector_magnitude > 1.001
    """)

    updated = 0
    errors  = 0
    batch   = cur.fetchmany(FETCH_SIZE)
    upd_cur = conn.cursor()

    while batch:
        for emb_id, vec_raw in batch:
            # pgvector는 '[f1,f2,...]' 문자열로 반환 — 파싱
            if isinstance(vec_raw, str):
                vec_raw = vec_raw.strip('[]').split(',')
            vec = np.array(vec_raw, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm < 1e-10:
                log.warning(f"vod_embedding_id={emb_id}: 영벡터(norm≈0) — 건너뜀")
                errors += 1
                continue
            vec_normalized = vec / norm
            try:
                upd_cur.execute("""
                    UPDATE vod_embedding
                    SET embedding        = %s::vector,
                        vector_magnitude = %s,
                        updated_at       = NOW()
                    WHERE vod_embedding_id = %s
                """, (to_pgvector_str(vec_normalized), float(np.linalg.norm(vec_normalized)), emb_id))
                updated += 1
            except Exception as e:
                log.error(f"UPDATE 실패 id={emb_id}: {e}")
                conn.rollback()
                errors += 1

        conn.commit()
        log.info(f"  정규화 진행: {updated:,}/{total:,}")
        batch = cur.fetchmany(FETCH_SIZE)

    log.info(f"정규화 완료: {updated:,}건 업데이트, {errors}건 오류")
    return updated


def create_index_after_ingest(conn):
    log.info("IVF_FLAT 인덱스 생성 중... (수 분 소요)")
    cur = conn.cursor()
    cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_vod_emb_ivfflat ON vod_embedding
            USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)
    """)
    conn.commit()
    log.info("인덱스 생성 완료")


def ingest_from_parquet(conn, parquet_path: str, dry_run: bool) -> tuple:
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

    # 컬럼 정규화: batch_embed.py 출력 형식 호환 (vector → embedding, full_asset_id/vod_id_fk → vod_id)
    if "vector" in df.columns and "embedding" not in df.columns:
        df = df.rename(columns={"vector": "embedding"})
    if "vod_id_fk" in df.columns and "vod_id" not in df.columns:
        df = df.rename(columns={"vod_id_fk": "vod_id"})
    if "full_asset_id" in df.columns and "vod_id" not in df.columns:
        df = df.rename(columns={"full_asset_id": "vod_id"})

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
    parser = argparse.ArgumentParser(description="pgvector DB 적재 (parquet → vod_embedding)")
    parser.add_argument('--file',         type=str, default='', help='특정 parquet 파일만 적재')
    parser.add_argument('--dry-run',      action='store_true',  help='DB INSERT 없이 확인만')
    parser.add_argument('--verify',       action='store_true',  help='적재 결과 검증만')
    parser.add_argument('--create-index', action='store_true',  help='적재 후 IVF_FLAT 인덱스 생성')
    parser.add_argument('--propagate',    action='store_true',
                        help='시리즈 대표 임베딩을 같은 series_nm 전체 vod_id에 복사 '
                             '(대표 적재 완료 후 실행)')
    parser.add_argument('--normalize',    action='store_true',
                        help='L2 정규화되지 않은 벡터(magnitude≠1.0)를 정규화 후 UPDATE')
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
            ins, skip, err = ingest_from_parquet(conn, args.from_parquet, args.dry_run)
            log.info(f"완료 — 삽입:{ins:,}  스킵:{skip}  오류:{err}")
            run_verify(conn)
            return

        # --propagate: 시리즈 전파만 실행
        if args.propagate:
            log.info("=== 시리즈 임베딩 전파 시작 ===")
            propagated = propagate_series_embeddings(conn, args.dry_run)
            log.info(f"전파 완료: {propagated:,}건")
            run_verify(conn)
            return

        if args.normalize:
            log.info("=== L2 정규화 시작 ===")
            updated = normalize_embeddings(conn, args.dry_run)
            log.info(f"정규화 완료: {updated:,}건")
            run_verify(conn)
            return

        parquet_files = get_parquet_files(DATA_DIR, args.file)
        if not parquet_files:
            log.error("적재할 parquet 파일 없음 — --file 옵션으로 경로 지정 또는 data/embeddings_*.parquet 배치")
            sys.exit(1)

        log.info(f"적재 대상 파일: {len(parquet_files)}개")
        if args.dry_run:
            log.info("[DRY-RUN] 실제 INSERT 없음")

        total_inserted = 0
        total_skipped  = 0
        total_errors   = 0

        for pq_path in parquet_files:
            log.info(f"처리 중: {pq_path.name}")
            ins, skip, err = ingest_parquet_file(conn, pq_path, args.dry_run)
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
