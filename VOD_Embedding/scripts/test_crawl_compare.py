"""
크롤링 전략 비교 테스트 (임시 스크립트)

BASE  : ytsearch3 + DURATION_MAX 600s
HINT  : BASE + 공중파(MBC/KBS/SBS/JTBC) 채널 힌트 쿼리 선두 삽입

실행:
    python scripts/test_crawl_compare.py               # 상위 20개 시리즈 비교
    python scripts/test_crawl_compare.py --limit 10    # 10개만
    python scripts/test_crawl_compare.py --delay 0     # 딜레이 없이 빠르게 (429 주의)
"""

import sys
import os
import re
import time
import random
import argparse
import logging
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv()  # CWD(레포 루트)에서 .env 탐색

# ── 파라미터 ─────────────────────────────────────────────────────────────────
DURATION_MIN_SEC  = 30
DURATION_MAX_SEC  = 600   # ← 기존 300 → 600 완화
N_SEARCH_RESULTS  = 3     # ← 기존 ytsearch1 → ytsearch3

PROVIDER_CHANNEL_HINT = {
    'MBC':  'MBC',
    'KBS':  'KBS',
    'SBS':  'SBS',
    'JTBC': 'JTBC',
}

logging.basicConfig(
    level=logging.WARNING,   # yt-dlp 노이즈 억제
    format='%(asctime)s [%(levelname)s] %(message)s',
)
log = logging.getLogger(__name__)


# ── DB 조회 ──────────────────────────────────────────────────────────────────
def fetch_sample(limit: int) -> list[dict]:
    """임베딩 없는 TV드라마 시리즈 상위 N개 (에피소드 수 내림차순, provider 포함)"""
    import psycopg2
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT v.series_nm, v.provider, COUNT(*) AS ep_cnt
        FROM vod v
        WHERE v.ct_cl = 'TV드라마'
          AND v.series_nm IS NOT NULL AND v.series_nm != ''
          AND NOT EXISTS (
              SELECT 1 FROM vod_embedding ve
              JOIN vod v2 ON ve.vod_id_fk = v2.full_asset_id
              WHERE v2.series_nm = v.series_nm AND v2.ct_cl = 'TV드라마'
          )
        GROUP BY v.series_nm, v.provider
        ORDER BY ep_cnt DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [{"series_nm": r[0], "provider": r[1], "ep_cnt": r[2]} for r in rows]


# ── 쿼리 생성 ─────────────────────────────────────────────────────────────────
def build_queries_base(series_nm: str) -> list[str]:
    return [
        f"{series_nm} 예고편",
        f"{series_nm} 하이라이트",
        f"{series_nm} 1회",
        f"{series_nm} trailer",
    ]


def build_queries_hint(series_nm: str, provider: str) -> list[str]:
    queries = []
    hint = PROVIDER_CHANNEL_HINT.get(provider)
    if hint:
        queries.append(f"{series_nm} 예고편 {hint}")  # 힌트 쿼리 선두
    queries.extend(build_queries_base(series_nm))
    return queries


# ── yt-dlp 검색 (메타데이터만, 다운로드 없음) ────────────────────────────────
def search_metadata(queries: list[str], delay: float) -> dict:
    """
    쿼리 목록 순서대로 시도.
    ytsearch{N}으로 N개 결과 중 duration 조건 통과하는 첫 번째 채택.
    download=False: 메타데이터만 조회 (속도 우선)
    """
    try:
        import yt_dlp
    except ImportError:
        return {"status": "error", "reason": "yt_dlp not installed"}

    ydl_opts = {
        'quiet':       True,
        'no_warnings': True,
        'skip_download': True,
        'socket_timeout': 15,
        'retries': 1,
    }

    for query in queries:
        if delay > 0:
            time.sleep(delay + random.uniform(0, 0.5))

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"ytsearch{N_SEARCH_RESULTS}:{query}",
                    download=False,
                )
                entries = info.get("entries") or []
                for entry in entries:
                    duration = entry.get("duration") or 0
                    if DURATION_MIN_SEC <= duration <= DURATION_MAX_SEC:
                        return {
                            "status":   "success",
                            "query":    query,
                            "duration": duration,
                            "title":    entry.get("title", "")[:50],
                        }
                # 이 쿼리의 모든 결과가 duration 실패
        except Exception as e:
            err = str(e)
            if '429' in err or 'Too Many Requests' in err:
                print("  [429] YouTube 속도 제한 — 60초 대기")
                time.sleep(60)
            continue

    return {"status": "failed"}


# ── 메인 ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="크롤링 전략 비교 테스트")
    parser.add_argument("--limit", type=int, default=20, help="테스트할 시리즈 수 (기본 20)")
    parser.add_argument("--delay", type=float, default=1.5, help="요청 간 딜레이(초) (기본 1.5)")
    args = parser.parse_args()

    print(f"\n{'='*70}")
    print(f" 크롤링 전략 비교: BASE vs HINT")
    print(f" ytsearch{N_SEARCH_RESULTS} / DURATION {DURATION_MIN_SEC}~{DURATION_MAX_SEC}s / 샘플 {args.limit}개")
    print(f"{'='*70}\n")

    sample = fetch_sample(args.limit)
    print(f"샘플 로드: {len(sample)}개 시리즈\n")

    results = []

    for i, vod in enumerate(sample, 1):
        series_nm = vod["series_nm"]
        provider  = vod["provider"]
        ep_cnt    = vod["ep_cnt"]
        has_hint  = provider in PROVIDER_CHANNEL_HINT

        print(f"[{i:2d}/{len(sample)}] {series_nm} ({provider}, {ep_cnt}화)", flush=True)

        # BASE
        q_base  = build_queries_base(series_nm)
        r_base  = search_metadata(q_base, args.delay)

        # HINT
        q_hint  = build_queries_hint(series_nm, provider)
        r_hint  = search_metadata(q_hint, args.delay)

        base_ok   = r_base["status"] == "success"
        hint_ok   = r_hint["status"] == "success"
        hint_diff = "(힌트쿼리)" if (has_hint and hint_ok and r_hint.get("query", "").endswith(provider)) else ""

        base_detail = ("→ " + r_base.get("query", "") + " (" + str(r_base.get("duration")) + "s)") if base_ok else "실패"
        hint_detail = ("→ " + r_hint.get("query", "") + " (" + str(r_hint.get("duration")) + "s) " + hint_diff) if hint_ok else "실패"
        foreign_tag = "  [힌트없음-해외]" if not has_hint else ""

        print(f"  BASE : {'✓' if base_ok else '✗'} {base_detail}")
        print(f"  HINT : {'✓' if hint_ok else '✗'} {hint_detail}{foreign_tag}")
        print()

        results.append({
            "series_nm": series_nm,
            "provider":  provider,
            "ep_cnt":    ep_cnt,
            "has_hint":  has_hint,
            "base_ok":   base_ok,
            "hint_ok":   hint_ok,
            "base_query": r_base.get("query", ""),
            "hint_query": r_hint.get("query", ""),
            "base_dur":  r_base.get("duration"),
            "hint_dur":  r_hint.get("duration"),
        })

    # ── 결과 요약 ──────────────────────────────────────────────────────────────
    total       = len(results)
    pubcaster   = [r for r in results if r["has_hint"]]
    foreign     = [r for r in results if not r["has_hint"]]

    base_total  = sum(1 for r in results   if r["base_ok"])
    hint_total  = sum(1 for r in results   if r["hint_ok"])
    base_pub    = sum(1 for r in pubcaster if r["base_ok"])
    hint_pub    = sum(1 for r in pubcaster if r["hint_ok"])
    base_for    = sum(1 for r in foreign   if r["base_ok"])
    hint_for    = sum(1 for r in foreign   if r["hint_ok"])

    hint_first  = sum(1 for r in pubcaster
                      if r["hint_ok"] and r["hint_query"] != r["base_query"])

    print(f"\n{'='*70}")
    print(f" 결과 요약")
    print(f"{'='*70}")
    print(f"  전체 ({total}개)    BASE: {base_total}/{total} ({base_total/total*100:.0f}%)"
          f"  HINT: {hint_total}/{total} ({hint_total/total*100:.0f}%)")
    if pubcaster:
        print(f"  공중파 ({len(pubcaster)}개)   BASE: {base_pub}/{len(pubcaster)} ({base_pub/len(pubcaster)*100:.0f}%)"
              f"  HINT: {hint_pub}/{len(pubcaster)} ({hint_pub/len(pubcaster)*100:.0f}%)")
        print(f"    → HINT 전용 성공 (BASE 실패, HINT 성공): "
              f"{sum(1 for r in pubcaster if not r['base_ok'] and r['hint_ok'])}개")
        print(f"    → HINT 쿼리로 먼저 찾은 경우: {hint_first}개")
    if foreign:
        print(f"  해외드라마 ({len(foreign)}개) BASE: {base_for}/{len(foreign)} ({base_for/len(foreign)*100:.0f}%)"
              f"  HINT: {hint_for}/{len(foreign)} ({hint_for/len(foreign)*100:.0f}%)")
    print(f"{'='*70}\n")

    # ── 실패 목록 ──────────────────────────────────────────────────────────────
    both_fail = [r for r in results if not r["base_ok"] and not r["hint_ok"]]
    if both_fail:
        print(f"두 전략 모두 실패한 시리즈 ({len(both_fail)}개):")
        for r in both_fail:
            print(f"  - {r['series_nm']} ({r['provider']}, {r['ep_cnt']}화)")
    print()


if __name__ == "__main__":
    main()
