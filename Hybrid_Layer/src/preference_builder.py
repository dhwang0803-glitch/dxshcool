"""Phase 2: watch_history × vod_tag → user_preference 집계.

유저별로 시청한 VOD의 태그를 집계하여 선호 프로필을 생성한다.
affinity = (해당 태그 시청 횟수 / 유저 전체 시청 횟수) × avg_completion 보정
watch_count >= 2 인 태그만 저장 (DDL CHECK 제약).
"""

import logging

log = logging.getLogger(__name__)


def build_user_preferences(conn, min_watch_count: int = 2) -> int:
    """watch_history × vod_tag 조인 집계 → user_preference UPSERT.

    SQL 기반 집계로 대량 데이터를 효율적으로 처리.

    Returns:
        적재된 레코드 수
    """
    log.info("Building user preferences (min_watch_count=%d)...", min_watch_count)

    with conn.cursor() as cur:
        # 기존 데이터 삭제 후 재적재 (전체 갱신)
        cur.execute("DELETE FROM public.user_preference")
        deleted = cur.rowcount
        log.info("Cleared %d existing user_preference rows", deleted)

        # SQL 기반 집계 + INSERT
        cur.execute(
            """
            INSERT INTO public.user_preference
                (user_id_fk, tag_category, tag_value, affinity, watch_count, avg_completion)
            SELECT
                agg.user_id_fk,
                agg.tag_category,
                agg.tag_value,
                -- affinity: 시청비중 × 평균완주율 보정 (0~1 정규화)
                LEAST(1.0,
                    (agg.tag_watch_count::REAL / user_total.total_watches)
                    * COALESCE(agg.avg_comp, 0.5)
                    * 2.0
                ),
                agg.tag_watch_count,
                agg.avg_comp
            FROM (
                SELECT
                    wh.user_id_fk,
                    vt.tag_category,
                    vt.tag_value,
                    COUNT(*)::SMALLINT AS tag_watch_count,
                    AVG(wh.completion_rate) AS avg_comp
                FROM public.watch_history wh
                JOIN public.vod_tag vt ON wh.vod_id_fk = vt.vod_id_fk
                GROUP BY wh.user_id_fk, vt.tag_category, vt.tag_value
                HAVING COUNT(*) >= %s
            ) agg
            JOIN (
                SELECT user_id_fk, COUNT(*) AS total_watches
                FROM public.watch_history
                GROUP BY user_id_fk
            ) user_total ON agg.user_id_fk = user_total.user_id_fk
            """,
            (min_watch_count,),
        )
        inserted = cur.rowcount
        conn.commit()

    log.info("Inserted %d user_preference rows", inserted)
    return inserted
