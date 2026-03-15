"""
VPC 업로드 완료 후 vod.poster_url 일괄 업데이트 (관리자 전용).
직접 실행 X — scripts/update_poster_url.py에서 import해서 사용.

업데이트 기준: series_nm 일치 + poster_url IS NULL
"""
import logging

logger = logging.getLogger(__name__)


def update_poster_urls(conn, mapping: dict) -> int:
    """
    series_nm → vpc_url 매핑으로 vod.poster_url 일괄 UPDATE.

    Args:
        conn: psycopg2 connection
        mapping: {series_nm: vpc_url}

    Returns:
        총 업데이트된 행 수
    """
    if not mapping:
        logger.warning("매핑이 비어 있습니다. 업데이트를 건너뜁니다.")
        return 0

    total_updated = 0
    with conn.cursor() as cur:
        for series_nm, vpc_url in mapping.items():
            cur.execute(
                """
                UPDATE vod
                SET poster_url = %s,
                    updated_at = NOW()
                WHERE series_nm = %s
                  AND poster_url IS NULL
                """,
                (vpc_url, series_nm),
            )
            rows = cur.rowcount
            total_updated += rows
            if rows:
                logger.debug("series_nm=%s → %d행 업데이트", series_nm, rows)

    conn.commit()
    logger.info("총 업데이트 행: %d (시리즈: %d건)", total_updated, len(mapping))
    return total_updated
