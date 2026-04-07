"""DB 연결 공통 모듈 — VectorSearchBase.get_conn() 하위 호환 별칭.

scripts/에서 sys.path로 Vector_Search를 추가한 경우와
프로젝트 루트에서 실행하는 경우 모두 지원.
"""

import os
import psycopg2


def get_connection():
    """pgvector 등록된 PostgreSQL 커넥션 반환."""
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
