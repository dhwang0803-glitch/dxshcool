"""verify_tmdb_matches.py — TMDB 매칭 검증 + 오매칭 poster NULL 처리.

문제: ct_cl이 키즈/TV연예오락 등인 VOD에 동명의 공포영화/외국영화 포스터가 매칭됨.
  - 헨젤과 그레텔(키즈) → 한국 공포영화 포스터
  - The Call(TV 연예/오락) → 한국 공포영화 포스터
  - 리얼리(기타) → 넷플릭스 좀비 드라마 포스터

검증 로직:
  1. 242건 suspect VOD를 TMDB 재검색
  2. ct_cl에 맞는 엔드포인트 사용 (TV계열→search/tv, 영화→search/movie)
  3. 장르 충돌 검사:
     - 키즈 VOD에 Horror/Thriller/Crime 장르 → 오매칭
     - TV 예능 VOD에 영화 결과만 → 오매칭
     - 제목 유사도 0.3 미만 → 오매칭
  4. 오매칭 확인된 VOD의 poster_url/backdrop_url NULL 처리

Usage:
    python Poster_Collection/scripts/verify_tmdb_matches.py --dry-run
    python Poster_Collection/scripts/verify_tmdb_matches.py
"""

import argparse
import json
import logging
import os
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

_root = Path(__file__).resolve().parents[2]
load_dotenv(_root / ".env")

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_BASE = "https://api.themoviedb.org/3"

# TMDB 장르 ID → 이름 (movie)
_MOVIE_GENRE_CONFLICT = {27: "Horror", 53: "Thriller", 80: "Crime", 10752: "War"}
# TMDB 장르 ID → 이름 (tv)
_TV_GENRE_CONFLICT = {10759: "Action & Adventure", 80: "Crime", 10768: "War & Politics"}

# ct_cl → 검색 엔드포인트
_TV_CT_CLS = frozenset({
    "TV드라마", "TV애니메이션", "키즈", "TV 시사/교양", "TV 연예/오락", "다큐", "교육",
})

# 키즈 VOD와 충돌하는 TMDB 장르 (movie + tv)
_KIDS_CONFLICT_GENRES = {27, 53, 80, 10752, 9648}  # Horror, Thriller, Crime, War, Mystery


def _title_sim(a: str, b: str) -> float:
    a = a.lower().strip()
    b = b.lower().strip()
    return SequenceMatcher(None, a, b).ratio()


def search_tmdb(series_nm: str, ct_cl: str) -> dict | None:
    """TMDB 검색 후 best match 반환."""
    is_tv = ct_cl in _TV_CT_CLS
    endpoint = f"{TMDB_BASE}/search/{'tv' if is_tv else 'movie'}"

    resp = requests.get(endpoint, params={
        "api_key": TMDB_API_KEY, "query": series_nm, "language": "ko-KR",
    }, timeout=10)
    if resp.status_code != 200:
        return None

    results = resp.json().get("results", [])
    if not results:
        return None

    # 유사도 기준 정렬
    title_key = "name" if is_tv else "title"
    orig_key = "original_name" if is_tv else "original_title"

    best = None
    best_sim = 0.0
    for item in results[:10]:
        names = [item.get(title_key, ""), item.get(orig_key, "")]
        names = [n for n in names if n]
        sim = max((_title_sim(series_nm, n) for n in names), default=0.0)
        if sim > best_sim:
            best_sim = sim
            best = item
            best["_sim"] = sim
            best["_type"] = "tv" if is_tv else "movie"

    return best


def check_conflict(item: dict, ct_cl: str) -> str | None:
    """TMDB 결과와 ct_cl 간 충돌 검사. 충돌 시 사유 반환."""
    if not item:
        return "TMDB 결과 없음 (기존 포스터 의심)"

    sim = item.get("_sim", 0.0)
    genre_ids = set(item.get("genre_ids", []))
    tmdb_type = item.get("_type", "")
    title = item.get("name") or item.get("title") or ""
    orig_lang = item.get("original_language", "")

    # 1. 제목 유사도 너무 낮으면 오매칭
    if sim < 0.4:
        return f"제목 유사도 낮음 ({sim:.2f}, TMDB: {title})"

    # 2. 키즈 VOD에 공포/스릴러/범죄 장르
    if ct_cl == "키즈" and genre_ids & _KIDS_CONFLICT_GENRES:
        conflict_names = [_MOVIE_GENRE_CONFLICT.get(g, str(g)) for g in genre_ids & _KIDS_CONFLICT_GENRES]
        return f"키즈에 {'/'.join(conflict_names)} 장르 (TMDB: {title})"

    # 3. 키즈 VOD인데 TMDB 결과가 movie (키즈는 보통 TV 시리즈)
    if ct_cl == "키즈" and tmdb_type == "movie":
        # 키즈 영화도 있으니 장르 충돌 없으면 pass
        if genre_ids & {16, 10751}:  # Animation, Family
            return None
        return f"키즈인데 영화 매칭, 비애니/비가족 (TMDB: {title})"

    # 4. TV 연예/오락인데 TMDB 장르가 공포/스릴러
    if ct_cl in ("TV 연예/오락", "TV 시사/교양") and genre_ids & _KIDS_CONFLICT_GENRES:
        conflict_names = [_MOVIE_GENRE_CONFLICT.get(g, _TV_GENRE_CONFLICT.get(g, str(g)))
                          for g in genre_ids & _KIDS_CONFLICT_GENRES]
        return f"예능/교양에 {'/'.join(conflict_names)} 장르 (TMDB: {title})"

    # 5. TV 계열 VOD인데 TMDB에서 TV 검색 결과가 전혀 다른 프로그램
    #    (original_language가 ko가 아니고 유사도가 중간 수준이면 의심)
    if ct_cl in _TV_CT_CLS and orig_lang != "ko" and sim < 0.7:
        return f"비한국 TV 매칭 (lang={orig_lang}, sim={sim:.2f}, TMDB: {title})"

    return None


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="DB 미반영, 검증만")
    args = parser.parse_args()

    # suspect 목록 로드
    suspect_path = _root / "Poster_Collection" / "data" / "suspect_tmdb_matches.json"
    with open(suspect_path, encoding="utf-8") as f:
        suspects = json.load(f)
    log.info("검증 대상: %d건", len(suspects))

    # TMDB 재검색 + 충돌 검사
    conflicts = []
    ok_count = 0
    for i, s in enumerate(suspects):
        series_nm = s["series_nm"]
        ct_cl = s["ct_cl"]

        item = search_tmdb(series_nm, ct_cl)
        reason = check_conflict(item, ct_cl)

        if reason:
            conflicts.append({"series_nm": series_nm, "ct_cl": ct_cl, "reason": reason})
            log.info("  [CONFLICT] %s (%s): %s", series_nm, ct_cl, reason)
        else:
            ok_count += 1

        if (i + 1) % 50 == 0:
            log.info("  진행 %d/%d (충돌=%d, 정상=%d)", i + 1, len(suspects), len(conflicts), ok_count)

        time.sleep(0.25)  # TMDB rate limit

    log.info("검증 완료: 충돌=%d, 정상=%d", len(conflicts), ok_count)

    if not conflicts:
        log.info("오매칭 없음")
        return

    # 결과 저장
    result_path = _root / "Poster_Collection" / "data" / "tmdb_conflicts.json"
    with open(result_path, "w", encoding="utf-8") as f:
        json.dump(conflicts, f, ensure_ascii=False, indent=2)
    log.info("충돌 목록 저장: %s", result_path)

    if args.dry_run:
        log.info("[DRY-RUN] DB 미반영. 위 목록 확인 후 --dry-run 제거하여 실행")
        return

    # DB poster NULL 처리
    conn = get_conn()
    conn.autocommit = True
    total_nulled = 0
    with conn.cursor() as cur:
        for c in conflicts:
            cur.execute(
                """UPDATE public.vod
                   SET poster_url = NULL, backdrop_url = NULL, updated_at = NOW()
                   WHERE series_nm = %s AND ct_cl = %s
                     AND (poster_url IS NOT NULL OR backdrop_url IS NOT NULL)""",
                (c["series_nm"], c["ct_cl"]),
            )
            total_nulled += cur.rowcount
    conn.close()
    log.info("DB poster NULL 처리: %d건", total_nulled)


if __name__ == "__main__":
    main()
