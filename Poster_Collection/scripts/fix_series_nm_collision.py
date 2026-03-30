"""fix_series_nm_collision.py — 동명이의 series_nm 분리 + 잘못된 포스터 NULL 처리.

문제: 같은 series_nm에 영화(GoodFellas)와 TV드라마(좋은 친구들)가 섞여있으면
      TMDB 검색 시 잘못된 포스터가 적용됨.

해결:
  1단계: 영화+TV가 혼재하는 series_nm 식별
  2단계: series_nm 분리 — "좋은 친구들" → "좋은 친구들(영화)", "좋은 친구들(TV드라마)"
         genre_detail에 방송국명이 있으면 TV계열로 확정
  3단계: 분리된 그룹의 poster_url/backdrop_url NULL 처리 (재크롤링 대상)

Usage:
    python Poster_Collection/scripts/fix_series_nm_collision.py --dry-run
    python Poster_Collection/scripts/fix_series_nm_collision.py
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

_root = Path(__file__).resolve().parents[2]
load_dotenv(_root / ".env")

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# TV 계열 ct_cl
_TV_CT_CLS = frozenset({
    "TV드라마", "TV애니메이션", "키즈", "TV 시사/교양", "TV 연예/오락", "다큐", "교육",
})

# genre_detail에 방송국명이 포함되면 TV 계열로 확정
_BROADCASTER_KEYWORDS = (
    "KBS", "MBC", "SBS", "tvN", "JTBC", "OCN", "채널A", "TV조선", "MBN",
    "EBS", "CJ", "지상파", "케이블",
)


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def find_collisions(conn) -> list[dict]:
    """영화+TV 혼재 series_nm 조회."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT series_nm,
                   array_agg(DISTINCT ct_cl) AS ct_cls,
                   COUNT(*) AS total
            FROM public.vod
            WHERE series_nm IS NOT NULL
            GROUP BY series_nm
            HAVING COUNT(DISTINCT ct_cl) > 1
            ORDER BY series_nm
        """)
        rows = cur.fetchall()
    return [{"series_nm": r[0], "ct_cls": r[1], "total": r[2]} for r in rows]


def rename_series_nm(conn, collisions: list[dict], dry_run: bool) -> int:
    """충돌하는 series_nm에 (ct_cl) 접미사 추가."""
    total_updated = 0
    with conn.cursor() as cur:
        for c in collisions:
            old_nm = c["series_nm"]
            for ct_cl in c["ct_cls"]:
                new_nm = f"{old_nm}({ct_cl})"
                if dry_run:
                    cur.execute(
                        "SELECT COUNT(*) FROM public.vod WHERE series_nm = %s AND ct_cl = %s",
                        (old_nm, ct_cl),
                    )
                    cnt = cur.fetchone()[0]
                    log.info("  [DRY-RUN] %s / %s → %s (%d건)", old_nm, ct_cl, new_nm, cnt)
                else:
                    cur.execute(
                        """UPDATE public.vod
                           SET series_nm = %s, updated_at = NOW()
                           WHERE series_nm = %s AND ct_cl = %s""",
                        (new_nm, old_nm, ct_cl),
                    )
                    total_updated += cur.rowcount
                    log.info("  %s / %s → %s (%d건)", old_nm, ct_cl, new_nm, cur.rowcount)
    if not dry_run:
        conn.commit()
    return total_updated


def null_posters_for_renamed(conn, collisions: list[dict], dry_run: bool) -> int:
    """분리된 series_nm의 poster_url/backdrop_url을 NULL로 초기화."""
    total_nulled = 0
    with conn.cursor() as cur:
        for c in collisions:
            old_nm = c["series_nm"]
            for ct_cl in c["ct_cls"]:
                new_nm = f"{old_nm}({ct_cl})"
                if dry_run:
                    cur.execute(
                        """SELECT COUNT(*) FROM public.vod
                           WHERE series_nm = %s
                             AND (poster_url IS NOT NULL OR backdrop_url IS NOT NULL)""",
                        (new_nm,),
                    )
                    cnt = cur.fetchone()[0]
                    if cnt:
                        log.info("  [DRY-RUN] %s: poster/backdrop NULL 대상 %d건", new_nm, cnt)
                else:
                    cur.execute(
                        """UPDATE public.vod
                           SET poster_url = NULL, backdrop_url = NULL, updated_at = NOW()
                           WHERE series_nm = %s
                             AND (poster_url IS NOT NULL OR backdrop_url IS NOT NULL)""",
                        (new_nm,),
                    )
                    total_nulled += cur.rowcount
    if not dry_run:
        conn.commit()
    return total_nulled


def null_wrong_posters(conn, dry_run: bool) -> int:
    """TMDB 직접 URL이 남아있는 serving VOD의 poster_url/backdrop_url을 NULL로 초기화.

    OCI URL이 아닌 tmdb.org 직접 URL은 이전 잘못된 매칭일 가능성이 높음.
    """
    with conn.cursor() as cur:
        if dry_run:
            cur.execute("""
                SELECT COUNT(*) FROM public.vod
                WHERE (poster_url LIKE '%%tmdb.org%%' OR backdrop_url LIKE '%%tmdb.org%%')
                  AND full_asset_id IN (
                    SELECT vod_id_fk FROM serving.popular_recommendation
                    UNION SELECT vod_id_fk FROM serving.hybrid_recommendation
                  )
            """)
            cnt = cur.fetchone()[0]
            log.info("  [DRY-RUN] serving VOD 중 TMDB 직접 URL: %d건 → NULL 대상", cnt)
            return cnt
        else:
            cur.execute("""
                UPDATE public.vod
                SET poster_url = CASE WHEN poster_url LIKE '%%tmdb.org%%' THEN NULL ELSE poster_url END,
                    backdrop_url = CASE WHEN backdrop_url LIKE '%%tmdb.org%%' THEN NULL ELSE backdrop_url END,
                    updated_at = NOW()
                WHERE (poster_url LIKE '%%tmdb.org%%' OR backdrop_url LIKE '%%tmdb.org%%')
                  AND full_asset_id IN (
                    SELECT vod_id_fk FROM serving.popular_recommendation
                    UNION SELECT vod_id_fk FROM serving.hybrid_recommendation
                  )
            """)
            cnt = cur.rowcount
            conn.commit()
            return cnt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="DB 미반영")
    parser.add_argument("--skip-tmdb-cleanup", action="store_true",
                        help="Step 4(TMDB URL NULL) 건너뛰기 — serving JOIN 경합 회피")
    args = parser.parse_args()

    conn = get_conn()

    # ── Step 1: 충돌 식별 ──
    log.info("[1/4] 영화+TV 혼재 series_nm 조회 중...")
    collisions = find_collisions(conn)
    log.info("  → %d개 series_nm 충돌 발견", len(collisions))
    for c in collisions[:10]:
        log.info("    %s: %s (%d건)", c["series_nm"], c["ct_cls"], c["total"])
    if len(collisions) > 10:
        log.info("    ... 외 %d건", len(collisions) - 10)

    if not collisions:
        log.info("충돌 없음")
        conn.close()
        return

    # ── Step 2: series_nm 분리 ──
    log.info("[2/4] series_nm 분리 (ct_cl 접미사 추가)...")
    renamed = rename_series_nm(conn, collisions, args.dry_run)
    if not args.dry_run:
        log.info("  → %d건 series_nm 업데이트", renamed)

    # ── Step 3: 분리된 그룹 포스터 NULL 처리 ──
    log.info("[3/4] 분리된 series_nm의 poster/backdrop NULL 처리...")
    nulled = null_posters_for_renamed(conn, collisions, args.dry_run)
    if not args.dry_run:
        log.info("  → %d건 poster/backdrop NULL 처리", nulled)

    # ── Step 4: TMDB 직접 URL 정리 (serving JOIN 필요 — 경합 시 건너뛰기) ──
    if args.skip_tmdb_cleanup:
        log.info("[4/4] --skip-tmdb-cleanup: TMDB URL 정리 건너뜀")
    else:
        log.info("[4/4] serving VOD 중 TMDB 직접 URL NULL 처리...")
        tmdb_nulled = null_wrong_posters(conn, args.dry_run)
        if not args.dry_run:
            log.info("  → %d건 TMDB URL NULL 처리", tmdb_nulled)

    conn.close()
    log.info("완료. 이후 fix_serving_posters.py 재실행하여 올바른 포스터 수집 필요.")


if __name__ == "__main__":
    main()
