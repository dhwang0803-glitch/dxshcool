"""
PLAN_01: watch_history 로더

watch_history 테이블에서 유저별 시청 이력을 읽어 반환한다.
completion_rate = 0인 행은 가중치 0이므로 제외.
대용량 대응: server-side cursor 사용 (메모리 절약).
"""
import logging

import psycopg2.extras

logger = logging.getLogger(__name__)


def load_watch_history(conn) -> dict[str, list[tuple[str, float]]]:
    """
    DB watch_history 테이블에서 유저별 시청 이력 로드.

    Returns:
        {user_id_fk: [(vod_id_fk, completion_rate), ...]}
        completion_rate > 0인 행만 포함.
    """
    logger.info("watch_history 로드 중 (server-side cursor)...")
    history: dict[str, list[tuple[str, float]]] = {}

    with conn.cursor("watch_history_cursor",
                     cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.itersize = 50_000
        cur.execute("""
            SELECT user_id_fk, vod_id_fk, completion_rate
            FROM watch_history
            WHERE completion_rate > 0
            ORDER BY user_id_fk, vod_id_fk
        """)
        for row in cur:
            uid = row["user_id_fk"]
            if uid not in history:
                history[uid] = []
            history[uid].append((row["vod_id_fk"], float(row["completion_rate"])))

    total_records = sum(len(v) for v in history.values())
    logger.info(
        f"watch_history 로드 완료: 유저 {len(history):,}명 / 시청 이력 {total_records:,}건"
    )
    if not history:
        logger.warning("watch_history 데이터가 없습니다.")
    return history
