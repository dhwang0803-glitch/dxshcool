"""
PLAN_04: 유저 임베딩 파이프라인 진입점 + DB 적재

실행:
    python scripts/run_embed.py              # 전체 유저 처리
    python scripts/run_embed.py --pilot 100  # 100명만 (파이럿)
    python scripts/run_embed.py --user-id <id>  # 특정 유저 재계산
    python scripts/run_embed.py --verify     # 적재 현황만 출력
"""
import argparse
import logging
import sys
import os

import numpy as np
import psycopg2.extras

# src/ 경로 추가 (scripts/에서 실행 시)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from db import get_conn
from data_loader import load_watch_history
from vod_embedding_loader import load_vod_combined
from user_embedder import build_user_embeddings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 1_000

UPSERT_SQL = """
INSERT INTO user_embedding (user_id_fk, embedding, vod_count, vector_magnitude, updated_at)
VALUES (%s, %s::vector, %s, %s, NOW())
ON CONFLICT (user_id_fk) DO UPDATE SET
    embedding        = EXCLUDED.embedding,
    vod_count        = EXCLUDED.vod_count,
    vector_magnitude = EXCLUDED.vector_magnitude,
    updated_at       = NOW()
"""


def _to_pgvector_str(vec: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.8f}" for x in vec.tolist()) + "]"


def save_user_embeddings(
    conn,
    user_vectors: dict[str, np.ndarray],
    vod_counts: dict[str, int],
) -> None:
    rows = [
        (uid, _to_pgvector_str(vec), vod_counts.get(uid, 0), 1.0)
        for uid, vec in user_vectors.items()
    ]
    total = len(rows)
    logger.info(f"DB 적재 시작: {total:,}건 (배치 크기 {BATCH_SIZE})")

    done = 0
    with conn.cursor() as cur:
        for i in range(0, total, BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            psycopg2.extras.execute_batch(cur, UPSERT_SQL, batch)
            conn.commit()
            done += len(batch)
            logger.info(f"  [{done:,}/{total:,}] {done / total * 100:.1f}%")

    logger.info(f"DB 적재 완료: {total:,}건")


def verify(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM user_embedding")
        count = cur.fetchone()[0]
        cur.execute(
            "SELECT user_id_fk, vod_count, vector_magnitude, updated_at "
            "FROM user_embedding LIMIT 3"
        )
        samples = cur.fetchall()
        cur.execute(
            "SELECT user_id_fk, vector_dims(embedding) AS dim "
            "FROM user_embedding LIMIT 1"
        )
        dim_row = cur.fetchone()

    logger.info("=== user_embedding 현황 ===")
    logger.info(f"  총 적재 건수: {count:,}")
    if dim_row:
        logger.info(f"  벡터 차원: {dim_row[1]}")
    logger.info("  샘플 (최대 3건):")
    for row in samples:
        logger.info(f"    user_id_fk={row[0]}  vod_count={row[1]}  magnitude={row[2]}  updated_at={row[3]}")


def run(pilot: int | None, user_id: str | None) -> None:
    logger.info("=== User_Embedding 파이프라인 시작 ===")

    with get_conn() as conn:
        # PLAN_01: watch_history 로드 (pilot/user_id는 DB 쿼리 단계에서 제한)
        history = load_watch_history(conn, user_limit=pilot, user_id=user_id)

        if not history:
            logger.warning("시청 이력 없음. 종료합니다.")
            return

        if user_id and user_id not in history:
            logger.error(f"user_id '{user_id}'의 시청 이력이 없습니다.")
            return
        if pilot:
            logger.info(f"파이럿 모드: {len(history):,}명")
        if user_id:
            logger.info(f"단일 유저 모드: {user_id}")

        # PLAN_02: 필요한 asset_ids만 조회 (메모리 절약)
        needed_assets = list({aid for items in history.values() for aid, _ in items})
        logger.info(f"필요한 VOD asset 수: {len(needed_assets):,}개")
        vod_vectors = load_vod_combined(conn, asset_ids=needed_assets)

        if not vod_vectors:
            logger.warning("결합 임베딩이 있는 VOD가 없습니다. 종료합니다.")
            return

        # PLAN_03: 유저 벡터 생성
        user_vectors, vod_counts = build_user_embeddings(history, vod_vectors)

        if not user_vectors:
            logger.warning("생성된 유저 임베딩이 없습니다. 종료합니다.")
            return

        # PLAN_04: DB 적재
        save_user_embeddings(conn, user_vectors, vod_counts)

    logger.info("=== 완료 ===")


def main() -> None:
    parser = argparse.ArgumentParser(description="유저 임베딩 생성 및 DB 적재")
    parser.add_argument("--pilot", type=int, metavar="N", help="N명 유저만 처리 (파이럿)")
    parser.add_argument("--user-id", type=str, help="특정 유저 1명 재계산")
    parser.add_argument("--verify", action="store_true", help="적재 현황만 출력")
    args = parser.parse_args()

    if args.verify:
        with get_conn() as conn:
            verify(conn)
        return

    run(pilot=args.pilot, user_id=args.user_id)


if __name__ == "__main__":
    main()
