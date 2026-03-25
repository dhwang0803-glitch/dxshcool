"""
테스터 계정 CF 후보 생성 → serving.vod_recommendation_test 적재

ALS 모델 학습에서 is_test=TRUE 유저가 제외되므로,
테스터의 watch_history 장르 선호도 기반 인기 VOD를 CF 대체 후보로 사용한다.

실행:
    cd <repo_root>
    python CF_Engine/scripts/gen_test_recommendations.py
    python CF_Engine/scripts/gen_test_recommendations.py --top-k 30
"""

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
    )


def build_test_recommendations(conn, top_k: int = 20) -> int:
    """테스터별 장르 선호도 기반 인기 VOD → vod_recommendation_test 적재.

    1. 테스터의 watch_history에서 ct_cl별 시청 비중 계산
    2. 비중 상위 장르의 인기 VOD(mv_vod_watch_stats)를 장르별 할당
    3. serving.vod_recommendation_test에 TRUNCATE + INSERT
    """
    cur = conn.cursor()

    # 테스터 목록
    cur.execute('SELECT sha2_hash FROM public."user" WHERE is_test = TRUE')
    testers = [r[0] for r in cur.fetchall()]
    log.info("테스터 %d명 대상 CF 대체 추천 생성 (top_k=%d)", len(testers), top_k)

    # 장르별 인기 VOD 풀 (mv_vod_watch_stats 기반, ct_cl별 top 200)
    cur.execute("""
        SELECT v.full_asset_id, v.ct_cl, s.total_watch_count,
               ROW_NUMBER() OVER (PARTITION BY v.ct_cl ORDER BY s.total_watch_count DESC) AS genre_rank
        FROM serving.mv_vod_watch_stats s
        JOIN public.vod v ON v.full_asset_id = s.vod_id_fk
        WHERE v.ct_cl IS NOT NULL
    """)
    popular_vods = cur.fetchall()  # (vod_id, ct_cl, watch_count, genre_rank)

    # ct_cl별 인기 VOD 사전
    from collections import defaultdict
    genre_pool: dict[str, list] = defaultdict(list)
    for vod_id, ct_cl, watch_count, _ in popular_vods:
        genre_pool[ct_cl].append((vod_id, watch_count))

    # TRUNCATE 테스트 테이블
    cur.execute("DELETE FROM serving.vod_recommendation_test WHERE user_id_fk = ANY(%s)", (testers,))
    log.info("기존 테스트 추천 삭제: %d건", cur.rowcount)

    records = []
    for uid in testers:
        # 유저 장르 선호도 (watch_history ct_cl 비중)
        cur.execute("""
            SELECT v.ct_cl, COUNT(*) as cnt
            FROM public.watch_history wh
            JOIN public.vod v ON v.full_asset_id = wh.vod_id_fk
            WHERE wh.user_id_fk = %s
            GROUP BY v.ct_cl
            ORDER BY cnt DESC
        """, (uid,))
        genre_counts = cur.fetchall()
        total = sum(c for _, c in genre_counts) or 1

        # 이미 시청한 VOD 제외
        cur.execute("SELECT vod_id_fk FROM public.watch_history WHERE user_id_fk = %s", (uid,))
        watched = {r[0] for r in cur.fetchall()}

        # 장르별 할당 비율로 top_k 채우기
        candidates = []
        for ct_cl, cnt in genre_counts:
            ratio = cnt / total
            quota = max(1, round(ratio * top_k))
            pool = [v for v, _ in genre_pool.get(ct_cl, []) if v not in watched]
            candidates.extend(pool[:quota])
            if len(candidates) >= top_k * 2:
                break

        # 중복 제거 + top_k 선별
        seen = set()
        unique = []
        for v in candidates:
            if v not in seen:
                seen.add(v)
                unique.append(v)
            if len(unique) >= top_k:
                break

        for rank, vod_id in enumerate(unique, 1):
            # score: 순위 기반 감소 (1.0 → 0.0)
            score = round(1.0 - (rank - 1) / top_k, 4)
            records.append({
                "user_id_fk": uid,
                "vod_id_fk": vod_id,
                "rank": rank,
                "score": score,
                "recommendation_type": "COLLABORATIVE",
            })

    if records:
        psycopg2.extras.execute_batch(
            cur,
            """
            INSERT INTO serving.vod_recommendation_test
                (user_id_fk, vod_id_fk, rank, score, recommendation_type,
                 expires_at)
            VALUES (%(user_id_fk)s, %(vod_id_fk)s, %(rank)s, %(score)s,
                    %(recommendation_type)s, NOW() + INTERVAL '30 days')
            ON CONFLICT (user_id_fk, vod_id_fk, recommendation_type)
            DO UPDATE SET rank=EXCLUDED.rank, score=EXCLUDED.score,
                          generated_at=NOW(), expires_at=EXCLUDED.expires_at
            """,
            records,
            page_size=500,
        )
    conn.commit()
    log.info("vod_recommendation_test 적재 완료: %d건 (%d명)", len(records), len(testers))
    return len(records)


def main():
    parser = argparse.ArgumentParser(description="테스터 CF 대체 추천 생성")
    parser.add_argument("--top-k", type=int, default=20, help="테스터별 추천 후보 수 (기본 20)")
    args = parser.parse_args()

    conn = get_conn()
    try:
        total = build_test_recommendations(conn, top_k=args.top_k)
        log.info("완료: %d건", total)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
