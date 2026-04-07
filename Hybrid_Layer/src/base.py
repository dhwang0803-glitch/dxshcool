"""Hybrid_Layer 공통 베이스 클래스.

DB 커넥션 관리 + test_mode 필터 + 배치 UPSERT 유틸리티를 제공한다.
모든 Phase별 서비스 클래스는 HybridBase를 상속한다.
"""

import os

import psycopg2
from dotenv import load_dotenv

load_dotenv()


class HybridBase:
    """Hybrid_Layer 공통 베이스."""

    @staticmethod
    def get_conn():
        """PostgreSQL 커넥션 반환."""
        return psycopg2.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", "5432")),
            dbname=os.getenv("DB_NAME"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
        )

    @staticmethod
    def is_test_filter(alias: str, test_mode: bool) -> str:
        """test_mode에 따른 SQL WHERE 조건 생성.

        Args:
            alias: SQL 테이블 별칭 (e.g., "u", "u2")
            test_mode: True이면 is_test=TRUE 유저만, False이면 is_test=FALSE 유저만

        Returns:
            "AND {alias}.is_test = TRUE/FALSE" SQL 조건절
        """
        return f"AND {alias}.is_test = TRUE" if test_mode else f"AND {alias}.is_test = FALSE"

    @staticmethod
    def batch_upsert(conn, sql_template: str, rows: list, format_str: str,
                     batch_size: int = 5000, commit_per_batch: bool = True) -> int:
        """배치 INSERT/UPSERT.

        Args:
            conn: psycopg2 커넥션
            sql_template: VALUES {args} 를 포함하는 SQL 템플릿
            rows: 삽입할 튜플 리스트
            format_str: mogrify 포맷 (e.g., "(%s,%s,%s)")
            batch_size: 배치 크기
            commit_per_batch: True이면 배치마다 커밋, False이면 호출자가 커밋

        Returns:
            총 삽입/갱신된 행 수
        """
        total = 0
        for i in range(0, len(rows), batch_size):
            batch = rows[i: i + batch_size]
            with conn.cursor() as cur:
                args = ",".join(
                    cur.mogrify(format_str, row).decode() for row in batch
                )
                cur.execute(sql_template.format(args=args))
                total += cur.rowcount
            if commit_per_batch:
                conn.commit()
        return total
