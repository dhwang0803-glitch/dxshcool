"""
시리즈 임베딩 전파 스크립트
현재 vod_embedding 테이블에 있는 임베딩을 동일 series_nm의 미적재 에피소드에 복사.

실행:
    python scripts/propagate_series.py --dry-run      # 전파 예정 건수만 확인
    python scripts/propagate_series.py                # 실제 전파 실행

동작:
    - vod_embedding에 임베딩이 있는 시리즈 조회
    - 같은 series_nm & ct_cl에서 아직 임베딩이 없는 vod_id에 복사 (INSERT ... SELECT)
    - TV 연예/오락 제외 (에피소드별 고유 콘텐츠)
    - series_nm이 NULL이거나 빈 문자열인 VOD 제외
    - ON CONFLICT DO NOTHING: 이미 적재된 행은 보존 (덮어쓰지 않음)

주의:
    - 팀원 전체 parquet 적재 완료 후 실행할 것
    - A파트 재적재 시: ingest_to_db.py --from-parquet 로 덮어쓴 뒤 본 스크립트 실행
"""

import sys
import os
import argparse
import logging
from pathlib import Path

from dotenv import load_dotenv

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

COMMIT_INTERVAL = 500

# 에피소드별 고유 콘텐츠 — 시리즈 전파 제외
EPISODE_EMBED_CT_CL = {'TV 연예/오락'}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def get_conn():
    import psycopg2
    from pgvector.psycopg2 import register_vector
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    register_vector(conn)
    return conn


def run_propagation(dry_run: bool) -> None:
    conn = get_conn()
    cur = conn.cursor()

    # 1. 임베딩 있는 시리즈 목록 조회 (TV 연예/오락 제외, series_nm 필수)
    cur.execute("""
        SELECT DISTINCT v.series_nm, v.ct_cl
        FROM vod_embedding ve
        JOIN vod v ON ve.vod_id_fk = v.full_asset_id
        WHERE v.series_nm IS NOT NULL
          AND v.series_nm != ''
          AND v.ct_cl NOT IN %s
        ORDER BY v.ct_cl, v.series_nm
    """, (tuple(EPISODE_EMBED_CT_CL),))
    series_list = cur.fetchall()

    log.info(f"임베딩 있는 시리즈 수: {len(series_list):,}개")

    total_propagated = 0
    total_already    = 0

    for series_nm, ct_cl in series_list:
        # 2. 해당 시리즈에서 아직 임베딩 없는 vod_id 수 확인
        cur.execute("""
            SELECT COUNT(*)
            FROM vod v
            WHERE v.series_nm = %s
              AND v.ct_cl = %s
              AND NOT EXISTS (
                  SELECT 1 FROM vod_embedding ve WHERE ve.vod_id_fk = v.full_asset_id
              )
        """, (series_nm, ct_cl))
        (missing_count,) = cur.fetchone()

        if missing_count == 0:
            total_already += 1
            continue

        if dry_run:
            log.info(f"[DRY-RUN] {ct_cl} / {series_nm}: {missing_count}개 전파 예정")
            total_propagated += missing_count
            continue

        # 3. 대표 임베딩 1개 선택 (updated_at DESC — 최신 적재 우선)
        cur.execute("""
            SELECT ve.vod_id_fk
            FROM vod_embedding ve
            JOIN vod v ON ve.vod_id_fk = v.full_asset_id
            WHERE v.series_nm = %s AND v.ct_cl = %s
            ORDER BY ve.updated_at DESC
            LIMIT 1
        """, (series_nm, ct_cl))
        row = cur.fetchone()
        if not row:
            continue
        rep_vod_id = row[0]

        # 4. INSERT ... SELECT: 대표 임베딩을 미적재 형제 vod_id들에 복사
        cur.execute("""
            INSERT INTO vod_embedding (
                vod_id_fk, embedding, embedding_type, embedding_dim,
                model_version, vector_magnitude, frame_count, source_type
            )
            SELECT
                sibling.full_asset_id,
                rep.embedding,
                rep.embedding_type,
                rep.embedding_dim,
                rep.model_version,
                rep.vector_magnitude,
                rep.frame_count,
                rep.source_type
            FROM vod sibling
            CROSS JOIN (
                SELECT embedding, embedding_type, embedding_dim,
                       model_version, vector_magnitude, frame_count, source_type
                FROM vod_embedding WHERE vod_id_fk = %s
            ) rep
            WHERE sibling.series_nm = %s
              AND sibling.ct_cl = %s
              AND NOT EXISTS (
                  SELECT 1 FROM vod_embedding ve WHERE ve.vod_id_fk = sibling.full_asset_id
              )
            ON CONFLICT (vod_id_fk) DO NOTHING
        """, (rep_vod_id, series_nm, ct_cl))

        propagated = cur.rowcount
        total_propagated += propagated

        if total_propagated % COMMIT_INTERVAL == 0:
            conn.commit()
            log.info(f"  진행: {total_propagated:,}건 전파 완료")

    if not dry_run:
        conn.commit()

    mode = "[DRY-RUN]" if dry_run else ""
    log.info(f"{mode} 전파 완료: {total_propagated:,}건 전파, {total_already}개 시리즈는 이미 완전 적재")

    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="시리즈 임베딩 전파")
    parser.add_argument("--dry-run", action="store_true",
                        help="실제 DB 변경 없이 전파 예정 건수만 출력")
    args = parser.parse_args()

    if args.dry_run:
        log.info("=== DRY-RUN 모드: DB 변경 없음 ===")

    run_propagation(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
