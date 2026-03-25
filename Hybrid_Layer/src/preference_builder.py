"""Phase 2: watch_history × vod_tag → user_preference 집계.

유저별로 시청한 VOD의 태그를 집계하여 선호 프로필을 생성한다.
affinity = (해당 태그 시청 횟수 / 유저 전체 시청 횟수) × avg_completion 보정
watch_count >= 2 인 태그만 저장 (DDL CHECK 제약).
"""

import logging

log = logging.getLogger(__name__)


def build_user_preferences(
    conn,
    min_watch_count: int = 2,
    test_mode: bool = False,
) -> int:
    """watch_history × vod_tag 조인 집계 → user_preference UPSERT.

    Args:
        test_mode: True이면 is_test=TRUE 유저만 처리 (테스터 격리용).
                   False(기본)이면 is_test=FALSE 실 유저만 처리.

    Returns:
        적재된 레코드 수
    """
    mode_label = "TEST 유저" if test_mode else "실 유저"
    log.info("Building user preferences (%s, min_watch_count=%d)...", mode_label, min_watch_count)

    is_test_filter = "AND u.is_test = TRUE" if test_mode else "AND u.is_test = FALSE"

    with conn.cursor() as cur:
        if test_mode:
            cur.execute("""
                DELETE FROM public.user_preference
                WHERE user_id_fk IN (
                    SELECT sha2_hash FROM public."user" WHERE is_test = TRUE
                )
            """)
        else:
            cur.execute("""
                DELETE FROM public.user_preference
                WHERE user_id_fk IN (
                    SELECT sha2_hash FROM public."user" WHERE is_test = FALSE
                )
            """)
        log.info("Cleared %d existing user_preference rows (%s)", cur.rowcount, mode_label)

        cur.execute(
            f"""
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
                JOIN public."user" u ON u.sha2_hash = wh.user_id_fk
                WHERE TRUE {is_test_filter}
                GROUP BY wh.user_id_fk, vt.tag_category, vt.tag_value
                HAVING COUNT(*) >= %s
            ) agg
            JOIN (
                SELECT wh2.user_id_fk, COUNT(*) AS total_watches
                FROM public.watch_history wh2
                JOIN public."user" u2 ON u2.sha2_hash = wh2.user_id_fk
                WHERE TRUE {is_test_filter}
                GROUP BY wh2.user_id_fk
            ) user_total ON agg.user_id_fk = user_total.user_id_fk
            """,
            (min_watch_count,),
        )
        inserted = cur.rowcount
        conn.commit()

    log.info("Inserted %d user_preference rows (%s)", inserted, mode_label)
    return inserted
