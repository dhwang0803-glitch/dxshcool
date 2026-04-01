"""
STEP 1: watch_history → User-Item 희소 행렬 변환
"""

import os
import logging
from dotenv import load_dotenv
import psycopg2
from scipy.sparse import csr_matrix
import numpy as np

log = logging.getLogger(__name__)


def get_conn():
    load_dotenv()
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
    )


def load_matrix(conn, alpha: float = 40, filter_quality: bool = False):
    """
    watch_history 전체 로드 → csr_matrix 반환

    Args:
        filter_quality: True이면 poster_url AND vod_embedding 둘 다 있는 VOD만 포함

    Returns:
        mat: csr_matrix (n_users x n_items), confidence = 1 + alpha * completion_rate
        user_encoder: {user_id_fk: row_idx}
        item_encoder: {vod_id_fk: col_idx}
        user_decoder: {row_idx: user_id_fk}
        item_decoder: {col_idx: vod_id_fk}
    """
    log.info("watch_history 로드 중%s...", " (품질 필터 ON)" if filter_quality else "")
    cur = conn.cursor()
    if filter_quality:
        cur.execute("""
            SELECT w.user_id_fk, w.vod_id_fk, w.completion_rate
            FROM watch_history w
            JOIN public.vod v ON w.vod_id_fk = v.full_asset_id
            JOIN public.vod_embedding ve ON w.vod_id_fk = ve.vod_id_fk
            JOIN public."user" u ON u.sha2_hash = w.user_id_fk
            WHERE w.completion_rate IS NOT NULL
              AND v.poster_url IS NOT NULL
              AND u.is_test = FALSE
        """)
    else:
        cur.execute("""
            SELECT w.user_id_fk, w.vod_id_fk, w.completion_rate
            FROM public.watch_history w
            JOIN public."user" u ON u.sha2_hash = w.user_id_fk
            WHERE w.completion_rate IS NOT NULL
              AND u.is_test = FALSE
        """)
    rows = cur.fetchall()
    cur.close()
    log.info("로드 완료: %d행", len(rows))

    user_ids = sorted(set(r[0] for r in rows))
    item_ids = sorted(set(r[1] for r in rows))

    user_encoder = {u: i for i, u in enumerate(user_ids)}
    item_encoder = {v: i for i, v in enumerate(item_ids)}
    user_decoder = {i: u for u, i in user_encoder.items()}
    item_decoder = {i: v for v, i in item_encoder.items()}

    u_idx = [user_encoder[r[0]] for r in rows]
    i_idx = [item_encoder[r[1]] for r in rows]
    conf  = [1.0 + alpha * float(r[2]) for r in rows]

    mat = csr_matrix(
        (conf, (u_idx, i_idx)),
        shape=(len(user_encoder), len(item_encoder)),
        dtype=np.float32,
    )

    sparsity = 1 - mat.nnz / (mat.shape[0] * mat.shape[1])
    log.info(
        "행렬: %d x %d  |  희소성: %.2f%%",
        mat.shape[0], mat.shape[1], sparsity * 100,
    )
    return mat, user_encoder, item_encoder, user_decoder, item_decoder
