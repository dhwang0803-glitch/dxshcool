"""Phase 4: 선호 태그별 VOD 추천 선반 생성.

user_preference → 유저별 top 5 태그
→ 태그별 vod_tag 매칭 + 시청 제외 + 랭킹
→ 태그별 top 10 VOD 선별
→ serving.tag_recommendation 적재
"""

import logging

log = logging.getLogger(__name__)


def build_tag_shelves(
    conn,
    top_tags: int = 5,
    vods_per_tag: int = 10,
    user_chunk_size: int = 1000,
) -> int:
    """전체 유저의 태그 선반 생성 → tag_recommendation 적재.

    Returns:
        총 적재 레코드 수
    """
    log.info("Phase 4: Building tag shelves (top_tags=%d, vods_per_tag=%d)", top_tags, vods_per_tag)

    with conn.cursor() as cur:
        # 대상 유저 (user_preference가 있는 유저)
        cur.execute("SELECT DISTINCT user_id_fk FROM public.user_preference")
        user_ids = [r[0] for r in cur.fetchall()]

    log.info("Target users: %d", len(user_ids))
    if not user_ids:
        return 0

    # 기존 데이터 삭제
    with conn.cursor() as cur:
        cur.execute("DELETE FROM serving.tag_recommendation")
        log.info("Cleared %d existing tag_recommendation rows", cur.rowcount)

    total_inserted = 0
    for chunk_start in range(0, len(user_ids), user_chunk_size):
        chunk = user_ids[chunk_start : chunk_start + user_chunk_size]
        batch_rows = []

        with conn.cursor() as cur:
            for uid in chunk:
                # 유저의 top N 태그 조회
                cur.execute(
                    """
                    SELECT tag_category, tag_value, affinity
                    FROM public.user_preference
                    WHERE user_id_fk = %s
                    ORDER BY affinity DESC
                    LIMIT %s
                    """,
                    (uid, top_tags),
                )
                top_tag_list = cur.fetchall()

                # 유저의 시청 이력 (제외용)
                cur.execute(
                    "SELECT vod_id_fk FROM public.watch_history WHERE user_id_fk = %s",
                    (uid,),
                )
                watched = {r[0] for r in cur.fetchall()}

                for tag_rank, (cat, val, aff) in enumerate(top_tag_list, 1):
                    # 해당 태그를 가진 VOD 중 미시청 + 인기순 정렬
                    cur.execute(
                        """
                        SELECT vt.vod_id_fk, vt.confidence
                        FROM public.vod_tag vt
                        WHERE vt.tag_category = %s AND vt.tag_value = %s
                        ORDER BY vt.confidence DESC
                        """,
                        (cat, val),
                    )
                    vod_rank = 0
                    for vod_row in cur.fetchall():
                        vid = vod_row[0]
                        if vid in watched:
                            continue
                        vod_rank += 1
                        if vod_rank > vods_per_tag:
                            break
                        # vod_score: confidence 기반 (추후 인기도 보정 가능)
                        vod_score = min(round(vod_row[1] * aff, 6), 1.0)
                        batch_rows.append((
                            uid, cat, val, tag_rank, round(aff, 6),
                            vid, vod_rank, vod_score,
                        ))

        # 배치 INSERT
        if batch_rows:
            with conn.cursor() as cur:
                args = ",".join(
                    cur.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", row).decode()
                    for row in batch_rows
                )
                cur.execute(
                    f"""
                    INSERT INTO serving.tag_recommendation
                        (user_id_fk, tag_category, tag_value, tag_rank, tag_affinity,
                         vod_id_fk, vod_rank, vod_score)
                    VALUES {args}
                    ON CONFLICT (user_id_fk, tag_category, tag_value, vod_id_fk) DO UPDATE SET
                        tag_rank = EXCLUDED.tag_rank,
                        tag_affinity = EXCLUDED.tag_affinity,
                        vod_rank = EXCLUDED.vod_rank,
                        vod_score = EXCLUDED.vod_score,
                        generated_at = NOW(),
                        expires_at = NOW() + INTERVAL '7 days'
                    """
                )
                total_inserted += cur.rowcount
            conn.commit()

        processed = min(chunk_start + user_chunk_size, len(user_ids))
        log.info("Progress: %d/%d users", processed, len(user_ids))

    log.info("Phase 4 완료: %d tag_recommendation rows", total_inserted)
    return total_inserted
