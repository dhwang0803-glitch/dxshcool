"""Vector_Search 공통 베이스 클래스.

DB 커넥션 관리 + 설정 로드 유틸리티를 제공한다.
모든 검색 엔진 클래스는 VectorSearchBase를 상속한다.
"""

import os
from pathlib import Path

import psycopg2
import yaml

CONFIG_PATH = Path(__file__).parent.parent / "config" / "search_config.yaml"


class VectorSearchBase:
    """Vector_Search 공통 베이스."""

    @staticmethod
    def get_conn():
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

    @staticmethod
    def load_config() -> dict:
        """search_config.yaml 설정 로드."""
        with open(CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f)
