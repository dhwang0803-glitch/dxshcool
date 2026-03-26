"""테스터별 유사 실유저 추천 복사.

테스터의 watch_history와 Jaccard 유사도가 가장 높은 실 유저를 찾아,
그 유저의 serving.vod_recommendation을 serving.vod_recommendation_test에 복사한다.

Usage:
    python CF_Engine/scripts/copy_similar_recommendations.py
"""

import logging
import os
import sys

from dotenv import load_dotenv
import psycopg2

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def get_conn():
    load_dotenv()
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
    )


def find_similar_user(cur, tester_id: str, tester_vods: set[str]) -> str | None:
    """Jaccard 유사도 기준 가장 유사한 실 유저 ID 반환."""
    if not tester_vods:
        log.warning("테스터 %s의 watch_history가 비어 있습니다.", tester_id[:16])
        return None

    # 테스터가 본 VOD를 하나라도 본 실 유저만 후보로 제한 (성능)
    cur.execute(
        """
        SELECT DISTINCT wh.user_id_fk
        FROM public.watch_history wh
        JOIN public."user" u ON u.sha2_hash = wh.user_id_fk
        WHERE wh.vod_id_fk = ANY(%s)
          AND u.is_test = FALSE
        """,
        (list(tester_vods),),
    )
    candidate_users = [r[0] for r in cur.fetchall()]

    if not candidate_users:
        log.warning("테스터 %s와 VOD 겹치는 실 유저 없음 — 전체에서 탐색", tester_id[:16])
        cur.execute(
            """
            SELECT DISTINCT wh.user_id_fk
            FROM public.watch_history wh
            JOIN public."user" u ON u.sha2_hash = wh.user_id_fk
            WHERE u.is_test = FALSE
            LIMIT 5000
            """
        )
        candidate_users = [r[0] for r in cur.fetchall()]

    if not candidate_users:
        return None

    # 후보 유저들의 watch VOD 로드
    cur.execute(
        """
        SELECT user_id_fk, vod_id_fk
        FROM public.watch_history
        WHERE user_id_fk = ANY(%s)
        """,
        (candidate_users,),
    )
    user_vods: dict[str, set] = {}
    for uid, vid in cur.fetchall():
        user_vods.setdefault(uid, set()).add(vid)

    # Jaccard 유사도 계산
    best_uid = None
    best_score = -1.0
    for uid, vods in user_vods.items():
        intersection = len(tester_vods & vods)
        union = len(tester_vods | vods)
        score = intersection / union if union > 0 else 0.0
        if score > best_score:
            best_score = score
            best_uid = uid

    log.info(
        "테스터 %s... → 유사 유저 %s... (Jaccard=%.4f, tester_vods=%d)",
        tester_id[:16], (best_uid or "")[:16], best_score, len(tester_vods),
    )
    return best_uid


def copy_recommendations(conn) -> int:
    """테스터 전원에 대해 유사 유저 추천을 vod_recommendation_test에 복사."""
    with conn.cursor() as cur:
        # 테스터 목록 조회
        cur.execute(
            """
            SELECT sha2_hash
            FROM public."user"
            WHERE is_test = TRUE
            """
        )
        tester_ids = [r[0] for r in cur.fetchall()]

    log.info("테스터 수: %d명", len(tester_ids))

    # 테스터별 watch_history 로드
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT user_id_fk, vod_id_fk
            FROM public.watch_history
            WHERE user_id_fk = ANY(%s)
            """,
            (tester_ids,),
        )
        tester_watch: dict[str, set] = {}
        for uid, vid in cur.fetchall():
            tester_watch.setdefault(uid, set()).add(vid)

    # 기존 vod_recommendation_test 초기화
    with conn.cursor() as cur:
        cur.execute("DELETE FROM serving.vod_recommendation_test")
        log.info("Cleared %d existing vod_recommendation_test rows", cur.rowcount)
    conn.commit()

    total_inserted = 0
    for tester_id in tester_ids:
        tester_vods = tester_watch.get(tester_id, set())

        with conn.cursor() as cur:
            similar_uid = find_similar_user(cur, tester_id, tester_vods)

        if similar_uid is None:
            log.warning("테스터 %s...의 유사 유저를 찾지 못했습니다.", tester_id[:16])
            continue

        # 유사 유저의 추천을 테스터 ID로 복사
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO serving.vod_recommendation_test
                    (user_id_fk, vod_id_fk, rank, score, recommendation_type, expires_at)
                SELECT
                    %s AS user_id_fk,
                    vod_id_fk,
                    rank,
                    score,
                    recommendation_type,
                    COALESCE(expires_at, NOW() + INTERVAL '7 days')
                FROM serving.vod_recommendation
                WHERE user_id_fk = %s
                ON CONFLICT (user_id_fk, vod_id_fk, recommendation_type) DO UPDATE SET
                    rank       = EXCLUDED.rank,
                    score      = EXCLUDED.score,
                    expires_at = EXCLUDED.expires_at
                """,
                (tester_id, similar_uid),
            )
            inserted = cur.rowcount
        conn.commit()

        log.info(
            "테스터 %s... → %d건 복사 (유사 유저: %s...)",
            tester_id[:16], inserted, similar_uid[:16],
        )
        total_inserted += inserted

    log.info("완료: vod_recommendation_test 총 %d건 적재", total_inserted)
    return total_inserted


def main():
    conn = get_conn()
    try:
        copy_recommendations(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
