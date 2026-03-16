"""
TMDB 시즌별 포스터 수집 모듈.

전략:
  1. search/tv 로 series_nm → TMDB series_id 확보
  2. /tv/{id} 로 시리즈 상세 조회 → seasons[].poster_path 에서 시즌 포스터 획득
  3. 시즌 포스터 없으면 시리즈 메인 poster_path로 fallback

사용 예:
    from Poster_Collection.src import tmdb_poster
    r = tmdb_poster.search("신서유기", season=2)
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


def _search_tv(series_nm: str) -> Optional[dict]:
    """TMDB search/tv → 최고 유사도 TV 결과 반환."""
    if not _tmdb_available():
        return None

    # 쿼리 변형: 원본 → 숫자 앞 공백 추가
    clean = series_nm.strip()
    spaced = re.sub(r'([가-힣A-Za-z])(\d)', r'\1 \2', clean)
    queries = list(dict.fromkeys([clean, spaced]))

    for lang in ("ko-KR", "en-US"):
        for query in queries:
            try:
                r = requests.get(
                    f"{_TMDB_URL}/search/tv",
                    params=_tmdb_params({"query": query, "language": lang, "page": 1}),
                    headers=_tmdb_headers(),
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code != 200:
                    continue
                results = r.json().get("results", [])
                if not results:
                    continue

                def _sim(item: dict, q: str = query) -> float:
                    names = [
                        item.get("name") or "",
                        item.get("original_name") or "",
                    ]
                    return max((_title_similarity(q, n) for n in names if n), default=0.0)

                best = max(results, key=_sim)
                if _sim(best) > 0.3:
                    return best
            except Exception as e:
                logger.debug("TMDB search 오류: %s", e)

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
    TMDB에서 시리즈 시즌별 포스터 URL 조회.

    Args:
        series_nm: DB series_nm (예: "신서유기")
        season: 시즌 번호 (기본 1)
        ct_cl: 콘텐츠 분류 (현재 미사용, 인터페이스 호환)
        release_year: 방영 연도 (현재 미사용, 인터페이스 호환)
        sleep: API 호출 간 딜레이

    Returns:
        {"image_url": str, "width": 500, "height": 750,
         "tmdb_id": int, "matched_name": str, "season_matched": bool}
        or None
    """
    if not _tmdb_available():
        logger.warning("TMDB API 키 없음 — TMDB_API_KEY 또는 TMDB_READ_ACCESS_TOKEN 설정 필요")
        return None

    # 1) TMDB에서 TV 시리즈 검색
    tv_result = _search_tv(series_nm)
    if not tv_result:
        return None

    tmdb_id = tv_result["id"]
    matched_name = tv_result.get("name") or tv_result.get("original_name") or ""

    if sleep > 0:
        time.sleep(sleep)

    # 2) 시리즈 상세 조회 → seasons 배열에서 시즌 포스터 추출
    detail = _get_tv_detail(tmdb_id)
    if not detail:
        # 상세 조회 실패 시 검색 결과의 poster_path 사용
        poster_path = tv_result.get("poster_path")
        if not poster_path:
            return None
        return {
            "image_url": f"{_IMG_BASE}{poster_path}",
            "width": 500,
            "height": 750,
            "tmdb_id": tmdb_id,
            "matched_name": matched_name,
            "season_matched": False,
        }

    # 시즌 포스터 찾기
    seasons = detail.get("seasons", [])
    season_poster = None
    for s in seasons:
        if s.get("season_number") == season and s.get("poster_path"):
            season_poster = s["poster_path"]
            break

    # fallback: 시리즈 메인 포스터
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
        "season_matched": season_poster is not None,
    }
