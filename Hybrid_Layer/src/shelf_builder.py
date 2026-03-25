"""Phase 4: 선호 태그별 VOD 추천 선반 생성.

user_preference → 유저별 top 5 태그
→ 태그별 vod_tag 매칭 + 시청 제외 + 랭킹
→ 태그별 top 10 VOD 선별
→ serving.tag_recommendation 적재

최적화 전략:
- 청크 내 등장하는 고유 (tag_category, tag_value)별로 상위 VOD를 한 번만 조회해 캐시
- 유저 루프에서는 캐시 조회 + 시청 이력 제외만 수행 (DB 왕복 없음)
- 청크 유저의 시청 이력은 watch_history 인덱스 조회로 한 번에 로드
"""

import logging

log = logging.getLogger(__name__)

# 태그당 VOD 후보 버퍼 (시청 제외 + 시리즈 중복제거 후 vods_per_tag개를 보장하기 위한 여유분)
_TAG_VOD_BUFFER = 500


def build_tag_shelves(
    conn,
    top_tags: int = 5,
    vods_per_tag: int = 10,
    user_chunk_size: int = 1000,
    test_mode: bool = False,
) -> int:
    """전체 유저의 태그 선반 생성 → tag_recommendation 적재.

    Args:
        test_mode: True이면 is_test=TRUE 유저만 처리 → tag_recommendation_test 적재.

    Returns:
        총 적재 레코드 수
    """
    dst_table = "serving.tag_recommendation_test" if test_mode else "serving.tag_recommendation"
    is_test_filter = "AND u.is_test = TRUE" if test_mode else "AND u.is_test = FALSE"
    mode_label = "TEST 유저" if test_mode else "실 유저"
    log.info("Phase 4: Building tag shelves (%s, top_tags=%d, vods_per_tag=%d)", mode_label, top_tags, vods_per_tag)

    with conn.cursor() as cur:
        cur.execute(
            f"""
            SELECT DISTINCT up.user_id_fk
            FROM public.user_preference up
            JOIN public."user" u ON u.sha2_hash = up.user_id_fk
            WHERE TRUE {is_test_filter}
            """
        )
        user_ids = [r[0] for r in cur.fetchall()]

    log.info("Target users: %d", len(user_ids))
    if not user_ids:
        return 0

    with conn.cursor() as cur:
        cur.execute(f"DELETE FROM {dst_table}")
        log.info("Cleared %d existing %s rows", cur.rowcount, dst_table)

    total_inserted = 0
    for chunk_start in range(0, len(user_ids), user_chunk_size):
        chunk = user_ids[chunk_start: chunk_start + user_chunk_size]

        with conn.cursor() as cur:
            # 1) 청크 유저의 top N 태그 한 번에 조회
            cur.execute(
                """
                SELECT user_id_fk, tag_category, tag_value, affinity,
                       ROW_NUMBER() OVER (
                           PARTITION BY user_id_fk ORDER BY affinity DESC
                       ) AS tag_rank
                FROM public.user_preference
                WHERE user_id_fk = ANY(%s)
                """,
                (chunk,),
            )
            rows = cur.fetchall()

        # user → [(tag_rank, cat, val, aff), ...]
        user_tags: dict[str, list] = {}
        unique_tags: set[tuple] = set()
        for user_id, cat, val, aff, tag_rank in rows:
            if tag_rank > top_tags:
                continue
            user_tags.setdefault(user_id, []).append((tag_rank, cat, val, aff))
            unique_tags.add((cat, val))

        if not unique_tags:
            processed = min(chunk_start + user_chunk_size, len(user_ids))
            log.info("Progress: %d/%d users", processed, len(user_ids))
            continue

        # 2) 청크 내 고유 태그별 상위 VOD를 한 번만 조회 (캐시)
        #    인기 태그(드라마 등) 수만 건 중 상위 _TAG_VOD_BUFFER개만 가져옴
        tag_vod_cache: dict[tuple, list[str]] = {}
        tag_list = list(unique_tags)
        tag_cats = [t[0] for t in tag_list]
        tag_vals = [t[1] for t in tag_list]

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.tag_category, t.tag_value, t.vod_id_fk,
                       v.ct_cl, v.series_nm
                FROM (
                    SELECT vt.tag_category, vt.tag_value, vt.vod_id_fk,
                           ROW_NUMBER() OVER (
                               PARTITION BY vt.tag_category, vt.tag_value
                               ORDER BY vt.confidence DESC
                           ) AS rn
                    FROM public.vod_tag vt
                    JOIN (
                        SELECT unnest(%s::varchar[]) AS tag_category,
                               unnest(%s::varchar[]) AS tag_value
                    ) ct ON ct.tag_category = vt.tag_category
                         AND ct.tag_value = vt.tag_value
                ) t
                JOIN public.vod v ON v.full_asset_id = t.vod_id_fk
                WHERE t.rn <= %s
                """,
                (tag_cats, tag_vals, _TAG_VOD_BUFFER),
            )
            for cat, val, vod_id, ct_cl, series_nm in cur.fetchall():
                tag_vod_cache.setdefault((cat, val), []).append(
                    (vod_id, ct_cl or "", series_nm or vod_id)
                )

        # 3) 청크 유저의 시청 이력 한 번에 로드
        with conn.cursor() as cur:
            cur.execute(
                "SELECT user_id_fk, vod_id_fk FROM public.watch_history WHERE user_id_fk = ANY(%s)",
                (chunk,),
            )
            watched: dict[str, set] = {}
            for user_id, vod_id in cur.fetchall():
                watched.setdefault(user_id, set()).add(vod_id)

        # 4) 유저별 선반 조립 (메모리 연산, DB 왕복 없음)
        batch_rows = []
        for user_id, tag_entries in user_tags.items():
            user_watched = watched.get(user_id, set())
            tag_entries.sort(key=lambda x: x[0])  # tag_rank 순

            for tag_rank, cat, val, aff in tag_entries:
                candidate_vods = tag_vod_cache.get((cat, val), [])
                vod_rank = 0
                seen_series: set = set()
                for vod_id, ct_cl, series_nm in candidate_vods:
                    if vod_id in user_watched:
                        continue
                    # 에피소드 단위 유지: actor 태그 + TV 연예/오락 조합만
                    # (특정 배우가 여러 예능에 게스트 출연한 에피소드 몰아보기 용도)
                    # 그 외 모든 경우(예능 장르 태그 포함)는 시리즈 단위 중복제거
                    # 에피소드 단위 유지:
                    # actor_guest(게스트 출연) + TV 연예/오락 → 배우/감독 팬에게 에피소드 몰아보기 제공
                    # director + TV 연예/오락 → 감독이 게스트 출연한 예능 에피소드 몰아보기
                    # actor_lead(주연)는 시리즈 중복제거 적용 (같은 예능 레귤러 10편 방지)
                    is_episode_level = (cat in ("actor_guest", "director") and ct_cl == "TV 연예/오락")
                    if not is_episode_level:
                        if series_nm in seen_series:
                            continue
                        seen_series.add(series_nm)
                    vod_rank += 1
                    if vod_rank > vods_per_tag:
                        break
                    vod_score = min(round(aff, 6), 1.0)
                    batch_rows.append((
                        user_id, cat, val, tag_rank, round(aff, 6),
                        vod_id, vod_rank, vod_score,
                    ))

        # 5) 배치 INSERT
        if batch_rows:
            with conn.cursor() as cur:
                args = ",".join(
                    cur.mogrify("(%s,%s,%s,%s,%s,%s,%s,%s)", row).decode()
                    for row in batch_rows
                )
                cur.execute(
                    f"""
                    INSERT INTO {dst_table}
                        (user_id_fk, tag_category, tag_value, tag_rank, tag_affinity,
                         vod_id_fk, vod_rank, vod_score)
                    VALUES {args}
                    ON CONFLICT (user_id_fk, tag_category, tag_value, vod_id_fk) DO UPDATE SET
                        tag_rank     = EXCLUDED.tag_rank,
                        tag_affinity = EXCLUDED.tag_affinity,
                        vod_rank     = EXCLUDED.vod_rank,
                        vod_score    = EXCLUDED.vod_score,
                        generated_at = NOW(),
                        expires_at   = NOW() + INTERVAL '7 days'
                    """
                )
                total_inserted += cur.rowcount
        conn.commit()

        processed = min(chunk_start + user_chunk_size, len(user_ids))
        log.info("Progress: %d/%d users", processed, len(user_ids))

    log.info("Phase 4 완료: %d tag_recommendation rows", total_inserted)
    return total_inserted
