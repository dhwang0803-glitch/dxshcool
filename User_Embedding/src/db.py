"""
DB 연결 헬퍼 (User_Embedding)
"""
import os
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv

load_dotenv()


def _get_conn_params() -> dict:
    return dict(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


@contextmanager
def get_conn():
    """트랜잭션 단위 연결 컨텍스트 매니저."""
    conn = psycopg2.connect(**_get_conn_params())
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
