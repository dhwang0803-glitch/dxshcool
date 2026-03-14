"""
STEP 6: 추천 결과 → serving.vod_recommendation upsert

실행: python scripts/export_to_db.py  (train.py 내부에서 호출)
"""

import logging
import psycopg2.extras

log = logging.getLogger(__name__)

INSERT_SQL = """
    INSERT INTO serving.vod_recommendation
        (user_id_fk, vod_id_fk, rank, score, recommendation_type)
    VALUES
        (%(user_id_fk)s, %(vod_id_fk)s, %(rank)s, %(score)s, %(recommendation_type)s)
"""

DELETE_SQL = """
    DELETE FROM serving.vod_recommendation
    WHERE recommendation_type = %s
      AND user_id_fk = ANY(%s)
"""


def export(conn, records: list[dict], batch_size: int = 1000,
           recommendation_type: str = "CF"):
    """
    기존 CF 추천 삭제 후 신규 INSERT (DELETE + INSERT 패턴).
    serving.vod_recommendation unique constraint 미확인으로 안전한 방식 사용.
    """
    if not records:
        log.warning("저장할 레코드 없음")
        return

    user_ids = list({r["user_id_fk"] for r in records})
    cur = conn.cursor()

    log.info("기존 CF 추천 삭제 중 (유저 %d명)...", len(user_ids))
    cur.execute(DELETE_SQL, (recommendation_type, user_ids))
    deleted = cur.rowcount
    log.info("삭제 완료: %d건", deleted)

    log.info("신규 추천 INSERT 중 (%d건, 배치 %d)...", len(records), batch_size)
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        psycopg2.extras.execute_batch(cur, INSERT_SQL, batch, page_size=batch_size)
        total += len(batch)
        log.info("  %d / %d", total, len(records))

    conn.commit()
    cur.close()
    log.info("DB 적재 완료: %d건", total)
