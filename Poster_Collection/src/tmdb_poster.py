"""
TMDB 포스터 수집 모듈 (ct_cl 기반 search/movie · search/tv 분리).

전략:
  1. ct_cl로 media_type 결정 → search/movie 또는 search/tv 엔드포인트 직접 호출
  2. ct_cl 없으면 search/multi fallback (기존 동작)
  3. movie → 바로 poster_path 사용
  4. tv    → /tv/{id} 상세 조회 → seasons[].poster_path 에서 시즌 포스터 획득
  5. 시즌 포스터 없으면 시리즈 메인 poster_path로 fallback

사용 예:
    from Poster_Collection.src import tmdb_poster
    r = tmdb_poster.search("신서유기", season=2, ct_cl="TV드라마")
    # -> {"image_url": "https://image.tmdb.org/t/p/w500/...", "width": 500, "height": 750}
"""

import logging
import os
import re
import time
from difflib import SequenceMatcher
from typing import Optional

import requests
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / "RAG" / "config" / "api_keys.env", override=False)

logger = logging.getLogger(__name__)

TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN", "")

_TMDB_URL = "https://api.themoviedb.org/3"
_IMG_BASE = "https://image.tmdb.org/t/p/w500"
_HEADERS = {"User-Agent": "vod-poster-pipeline/1.0"}
REQUEST_TIMEOUT = 8


def _tmdb_headers() -> dict:
    """TMDB 인증 헤더. Read Access Token(v4 Bearer) 우선."""
    h = dict(_HEADERS)
    if TMDB_READ_ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {TMDB_READ_ACCESS_TOKEN}"
    return h


def _tmdb_params(extra: dict | None = None) -> dict:
    """TMDB 공통 파라미터. Bearer 없을 때만 api_key 추가."""
    p = extra or {}
    if not TMDB_READ_ACCESS_TOKEN and TMDB_API_KEY:
        p["api_key"] = TMDB_API_KEY
    return p


def _tmdb_available() -> bool:
    return bool(TMDB_READ_ACCESS_TOKEN or TMDB_API_KEY)


def _title_similarity(a: str, b: str) -> float:
    """두 제목의 유사도 (0.0~1.0)."""
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return len_ratio
    return SequenceMatcher(None, a, b).ratio()


def _item_names(item: dict) -> list[str]:
    """media_type에 관계없이 제목 후보 반환."""
    candidates = [
        item.get("name") or "",
        item.get("original_name") or "",
        item.get("title") or "",
        item.get("original_title") or "",
    ]
    return [n for n in candidates if n]


# ct_cl → TMDB media_type 매핑
_CT_CL_MEDIA = {
    "영화":        "movie",
    "TV드라마":    "tv",
    "TV애니메이션": "tv",
    "키즈":        "tv",
    "TV 시사/교양": "tv",
    "TV 연예/오락": "tv",
    "공연/음악":   "movie",
    "다큐":        "tv",
    "교육":        "tv",
}

_SIM_THRESHOLD = 0.5


def _search_by_type(series_nm: str, ct_cl: str = None) -> Optional[dict]:
    """ct_cl 기반으로 search/movie 또는 search/tv 엔드포인트 직접 호출.

    ct_cl이 없으면 search/multi fallback.
    유사도 0.5 이상인 결과 중 최고 유사도 항목 반환.
    """
    if not _tmdb_available():
        return None

    clean = series_nm.strip()
    spaced = re.sub(r'([가-힣A-Za-z])(\d)', r'\1 \2', clean)
    queries = list(dict.fromkeys([clean, spaced]))

    media_hint = _CT_CL_MEDIA.get(ct_cl) if ct_cl else None
    if media_hint:
        endpoint = f"{_TMDB_URL}/search/{'movie' if media_hint == 'movie' else 'tv'}"
    else:
        endpoint = f"{_TMDB_URL}/search/multi"

    for lang in ("ko-KR", "en-US"):
        for query in queries:
            try:
                r = requests.get(
                    endpoint,
                    params=_tmdb_params({"query": query, "language": lang, "page": 1}),
                    headers=_tmdb_headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    continue
                results = r.json().get("results", [])
                if not media_hint:
                    # search/multi: person 제외
                    results = [x for x in results if x.get("media_type") in ("movie", "tv")]
                if not results:
                    continue

                def _sim(item: dict, q: str = query) -> float:
                    names = _item_names(item)
                    return max((_title_similarity(q, n) for n in names), default=0.0)

                best = max(results, key=_sim)
                if _sim(best) >= _SIM_THRESHOLD:
                    # search/movie, search/tv 결과에는 media_type이 없으므로 설정
                    if media_hint and "media_type" not in best:
                        best["media_type"] = media_hint
                    return best
            except Exception as e:
                logger.debug("TMDB search 오류 (%s): %s", endpoint, e)

    return None


def _get_tv_detail(tmdb_id: int) -> Optional[dict]:
    """TMDB /tv/{id} 호출 → 시리즈 상세 (seasons 배열 포함)."""
    try:
        r = requests.get(
            f"{_TMDB_URL}/tv/{tmdb_id}",
            params=_tmdb_params({"language": "ko-KR"}),
            headers=_tmdb_headers(),
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        logger.debug("TMDB tv detail 오류: %s", e)
        return None


def search(
    series_nm: str,
    season: int = 1,
    ct_cl: str = None,
    release_year: int = None,
    sleep: float = 0.25,
) -> Optional[dict]:
    """
    ct_cl 기반 TMDB 검색으로 포스터 URL 조회 (movie/tv 엔드포인트 분리).

    Returns:
        {"image_url": str, "width": 500, "height": 750,
         "tmdb_id": int, "matched_name": str,
         "media_type": "movie"|"tv", "season_matched": bool}
        or None
    """
    if not _tmdb_available():
        logger.warning("TMDB API 키 없음 — TMDB_API_KEY 또는 TMDB_READ_ACCESS_TOKEN 설정 필요")
        return None

    result = _search_by_type(series_nm, ct_cl=ct_cl)
    if not result:
        return None

    media_type = result["media_type"]
    tmdb_id = result["id"]
    matched_name = (
        result.get("title") or result.get("name")
        or result.get("original_title") or result.get("original_name") or ""
    )

    # ── movie: 바로 poster_path 사용 ──
    if media_type == "movie":
        poster_path = result.get("poster_path")
        if not poster_path:
            return None
        return {
            "image_url": f"{_IMG_BASE}{poster_path}",
            "width": 500,
            "height": 750,
            "tmdb_id": tmdb_id,
            "matched_name": matched_name,
            "media_type": "movie",
            "season_matched": False,
        }

    # ── tv: 시즌 포스터 시도 → fallback 메인 포스터 ──
    if sleep > 0:
        time.sleep(sleep)

    detail = _get_tv_detail(tmdb_id)
    if not detail:
        poster_path = result.get("poster_path")
        if not poster_path:
            return None
        return {
            "image_url": f"{_IMG_BASE}{poster_path}",
            "width": 500,
            "height": 750,
            "tmdb_id": tmdb_id,
            "matched_name": matched_name,
            "media_type": "tv",
            "season_matched": False,
        }

    seasons = detail.get("seasons", [])
    season_poster = None
    for s in seasons:
        if s.get("season_number") == season and s.get("poster_path"):
            season_poster = s["poster_path"]
            break

    main_poster = detail.get("poster_path")
    poster_path = season_poster or main_poster

    if not poster_path:
        return None

    return {
        "image_url": f"{_IMG_BASE}{poster_path}",
        "width": 500,
        "height": 750,
        "tmdb_id": tmdb_id,
        "matched_name": matched_name,
        "media_type": "tv",
        "season_matched": season_poster is not None,
    }
