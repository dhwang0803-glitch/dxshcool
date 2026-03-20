"""
DB 연결 공통 모듈
"""
import os
import getpass
from contextlib import contextmanager

import pandas as pd
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


def load_watch_stats(conn) -> pd.DataFrame:
    """
    watch_history에서 VOD별 시청 통계 집계.

    반환 컬럼:
        vod_id_fk         — VOD ID
        watch_count       — 전체 시청 수
        watch_count_7d    — 최근 7일 시청 수
        avg_completion_rate — 평균 완주율
        avg_satisfaction    — 평균 만족도
    """
    query = """
        SELECT
            vod_id_fk,
            COUNT(*)                                                         AS watch_count,
            COUNT(*) FILTER (WHERE strt_dt >= NOW() - INTERVAL '7 days')    AS watch_count_7d,
            AVG(completion_rate)                                             AS avg_completion_rate,
            AVG(satisfaction)                                                AS avg_satisfaction
        FROM public.watch_history
        GROUP BY vod_id_fk
    """
    return pd.read_sql(query, conn)
