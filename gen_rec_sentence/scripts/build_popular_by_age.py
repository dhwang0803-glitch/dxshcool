"""age_grp10별 인기 VOD top 20 → serving.popular_by_age 적재.

콜드스타트 유저(user_segment 미보유)의 추천 fallback 풀 생성.
watch_history × user.age_grp10 기준 시청 횟수 상위 VOD를 연령대별로 적재.

Usage:
    python gen_rec_sentence/scripts/build_popular_by_age.py
    python gen_rec_sentence/scripts/build_popular_by_age.py --top-n 20 --dry-run
"""

import argparse
import logging
import sys

import psycopg2.extras

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(".env")

from gen_rec_sentence.src.context_builder import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_DEFAULT_TOP_N = 20


def build(conn, top_n: int, dry_run: bool) -> None:
    log.info("age_grp10별 인기 VOD top %d 집계 중...", top_n)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT u.age_grp10, wh.vod_id_fk, COUNT(*) AS watch_cnt
            FROM public.watch_history wh
            JOIN public.user u ON u.sha2_hash = wh.user_id_fk
            JOIN public.vod v ON v.full_asset_id = wh.vod_id_fk
            WHERE v.poster_url IS NOT NULL
              AND v.smry IS NOT NULL AND v.smry != ''
              AND u.age_grp10 IS NOT NULL
            GROUP BY u.age_grp10, wh.vod_id_fk
            ORDER BY u.age_grp10, watch_cnt DESC
            """
        )
        rows = cur.fetchall()

    # age_grp10별 top_n 추출
    age_map: dict[str, list[tuple]] = {}
    for age_grp, vod_id, cnt in rows:
        if age_grp not in age_map:
            age_map[age_grp] = []
        if len(age_map[age_grp]) < top_n:
            age_map[age_grp].append((vod_id, cnt))

    total = sum(len(v) for v in age_map.values())
    log.info("집계 완료: %d개 연령대 × 최대 %d VOD = %d건", len(age_map), top_n, total)
    for age, vods in sorted(age_map.items()):
        log.info("  %s: %d VOD (1위 시청수=%d)", age, len(vods), vods[0][1] if vods else 0)

    if dry_run:
        log.info("[DRY-RUN] 실제 적재 없이 종료")
        return

    # UPSERT
    insert_rows = []
    for age_grp, vods in age_map.items():
        for rank, (vod_id, cnt) in enumerate(vods, start=1):
            insert_rows.append((age_grp, rank, vod_id, float(cnt)))

    with conn.cursor() as cur:
        cur.execute("TRUNCATE serving.popular_by_age")
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO serving.popular_by_age (age_grp10, rank, vod_id_fk, score)
            VALUES %s
            """,
            insert_rows,
        )
    conn.commit()
    log.info("serving.popular_by_age 적재 완료: %d행", len(insert_rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="age_grp10별 인기 VOD 적재")
    parser.add_argument("--top-n", type=int, default=_DEFAULT_TOP_N)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_conn()
    try:
        build(conn, top_n=args.top_n, dry_run=args.dry_run)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
