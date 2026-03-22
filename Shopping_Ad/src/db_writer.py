"""seasonal_market 테이블 UPSERT 모듈."""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv()

UPSERT_SQL = """
INSERT INTO seasonal_market (
    channel, broadcast_date, start_time, end_time, product_name
)
VALUES (
    %(channel)s, %(broadcast_date)s, %(start_time)s, %(end_time)s,
    %(product_name)s
)
ON CONFLICT (channel, broadcast_date, start_time, product_name)
DO UPDATE SET
    end_time   = EXCLUDED.end_time,
    crawled_at = NOW()
"""


@contextmanager
def get_conn():
    """psycopg2 커넥션 컨텍스트 매니저."""
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def upsert_products(conn, products: list[dict]) -> int:
    """seasonal_market UPSERT. 적재 건수를 반환."""
    if not products:
        return 0

    cur = conn.cursor()
    count = 0
    try:
        for row in products:
            params = {
                "channel": row.get("channel"),
                "broadcast_date": row.get("broadcast_date"),
                "start_time": row.get("start_time"),
                "end_time": row.get("end_time"),
                "product_name": row.get("product_name"),
            }
            cur.execute(UPSERT_SQL, params)
            count += 1

        conn.commit()
        logger.info("DB 적재 완료: %d건", count)
    except Exception:
        conn.rollback()
        logger.exception("DB 적재 실패")
        raise
    finally:
        cur.close()

    return count
