"""CF_Engine 공통 베이스 클래스.

DB 커넥션 관리를 제공한다.
모든 CF 서비스 클래스는 CFBase를 상속한다.
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


class CFBase:
    """CF_Engine 공통 베이스."""

    @staticmethod
    def get_conn():
        """PostgreSQL 커넥션 반환."""
        return psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=os.getenv("DB_PORT"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            dbname=os.getenv("DB_NAME"),
        )
