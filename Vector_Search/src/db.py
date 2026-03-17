import os
import psycopg2
from pgvector.psycopg2 import register_vector


def get_connection():
    """
    .env 기반 DB 연결 반환.
    호출부에서 conn.close() 책임.
    """
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    register_vector(conn)
    return conn
