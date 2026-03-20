"""
DB 연결 공통 모듈
"""
import os
import getpass
from contextlib import contextmanager

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST     = os.getenv("DB_HOST")
DB_PORT     = int(os.getenv("DB_PORT", "5432"))
DB_NAME     = os.getenv("DB_NAME")
DB_USER     = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

_password_cache = None


def _get_password() -> str:
    global _password_cache
    if DB_PASSWORD:
        return DB_PASSWORD
    if _password_cache is None:
        _password_cache = getpass.getpass("PostgreSQL 비밀번호 입력: ")
    return _password_cache


@contextmanager
def get_conn():
    """트랜잭션 단위 연결 컨텍스트 매니저"""
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=_get_password(),
    )
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
