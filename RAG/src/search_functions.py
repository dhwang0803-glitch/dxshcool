"""
search_functions.py — 외부 소스 메타데이터 검색

소스 전략 (Wikipedia/IMDB 제거):
  1. TMDB  (The Movie Database)  — 영화 + TV 드라마 구조적 데이터
  2. KMDB  (한국영상자료원)         — 한국 콘텐츠 특화
  3. AI-Hub (문화콘텐츠 스토리 데이터) — 로컬 JSON 데이터셋 (선택)
  4. Ollama exaone3.5            — 최종 LLM 폴백

에피소드 제목 정규화: "명탐정코난 19기 59회" → "명탐정코난" 후 검색
"""
import os
import re
import json
import logging
import functools
from pathlib import Path
from typing import Optional, List

import requests
from dotenv import load_dotenv

# 프로젝트 루트 .env 우선 로드
_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_ROOT / ".env")
load_dotenv(_ROOT / "RAG" / "config" / "api_keys.env", override=False)

from validation import VALID_RATINGS, validate_director, validate_cast, validate_rating, validate_date

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────

TMDB_API_KEY          = os.getenv("TMDB_API_KEY", "")
TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN", "")
KMDB_API_KEY          = os.getenv("KMDB_API_KEY", "")
OLLAMA_HOST           = os.getenv("OLLAMA_HOST",  "http://localhost:11434")
OLLAMA_MODEL          = os.getenv("OLLAMA_MODEL", "exaone3.5:7.8b")
REQUEST_TIMEOUT       = 8

_AIHUB_PATH = _ROOT / "RAG" / "data" / "aihub_cultural.json"

_HEADERS  = {"User-Agent": "vod-rag-pipeline/1.0"}
_TMDB_URL = "https://api.themoviedb.org/3"
_KMDB_URL = "http://api.koreafilm.or.kr/openapi-data2/wisenut/search_api/search_json2.jsp"

# TMDB 한국 등급 → 내부 표준
_TMDB_KR_RATING = {
    "ALL": "전체이용가",
    "12":  "12세이용가",
    "15":  "15세이용가",
    "청":  "청소년관람불가",
    "18":  "청소년관람불가",
}
# TMDB US 등급 → 내부 표준 (한국 등급 없을 때 폴백)
_TMDB_US_RATING = {
    "G":     "전체이용가",
    "PG":    "12세이용가",
    "PG-13": "15세이용가",
    "R":     "청소년관람불가",
    "NC-17": "청소년관람불가",
}

# ─────────────────────────────────────────
# 인메모리 캐시
# ─────────────────────────────────────────

_cache: dict = {}

def _cached(fn):
    @functools.wraps(fn)
    def wrapper(*args):
        key = (fn.__name__,) + args
        if key not in _cache:
            _cache[key] = fn(*args)
        return _cache[key]
    return wrapper


# ─────────────────────────────────────────
# 에피소드 번호 제거
# ─────────────────────────────────────────

_RE_EPISODE = re.compile(
    r'\s*[\(\[]?(?:\d{1,4}화|제?\d{1,4}회\.?|[Ss]\d{1,2}[Ee]\d{1,3}|'
    r'시즌\s*\d+|Season\s*\d+|\d+기|\d+편)[\)\]]?\s*\.?$',
    re.IGNORECASE,
)

def _strip_episode(title: str) -> str:
    """'명탐정코난 19기 59회' → '명탐정코난'  반복 적용으로 중첩 제거.
    제거 후 빈 문자열이 되면 원본 반환."""
    prev, t = None, title.strip()
    while t != prev:
        prev = t
        t = _RE_EPISODE.sub("", t).strip()
    return t if t else title.strip()


# ─────────────────────────────────────────
# TMDB 헬퍼
# ─────────────────────────────────────────

def _tmdb_headers() -> dict:
    """TMDB 인증 헤더 반환. Read Access Token(v4 Bearer) 우선, 없으면 빈 dict."""
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
    """두 제목의 유사도 (0.0~1.0).
    완전 일치 > 비슷한 길이의 포함 > 글자 집합 겹침.
    결과 제목이 쿼리보다 훨씬 길면 페널티 (메이킹/다큐 오매칭 방지).
    """
    a, b = a.lower().strip(), b.lower().strip()
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    # 길이 비율 페널티: 결과가 쿼리보다 2배 이상 길면 감점
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return len_ratio  # 포함되더라도 길이 비율만큼만 점수
    return len(set(a) & set(b)) / max(len(set(a)), len(set(b))) * len_ratio


def _tmdb_search(title: str) -> Optional[dict]:
    """TMDB multi search → 제목 유사도 기반으로 가장 관련성 높은 결과 반환 (movie / tv)"""
    if not _tmdb_available():
        return None
    clean = _strip_episode(title)
    # 숫자 앞 공백 변형: "겨울왕국2" → "겨울왕국 2"
    spaced = re.sub(r'([가-힣A-Za-z])(\d)', r'\1 \2', clean)
    for query in dict.fromkeys([clean, spaced, title]):  # 에피소드 제거본 우선
        try:
            r = requests.get(
                f"{_TMDB_URL}/search/multi",
                params=_tmdb_params({"query": query, "language": "ko-KR", "page": 1}),
                headers=_tmdb_headers(), timeout=REQUEST_TIMEOUT,
            )
            if r.status_code != 200:
                logger.debug("TMDB search HTTP %s: %s", r.status_code, r.text[:100])
                continue
            results = r.json().get("results", [])
            candidates = [r for r in results if r.get("media_type") in ("movie", "tv")]
            if not candidates:
                continue
            # 제목 유사도 기준 정렬 — 오매칭(메이킹, 다큐 등) 방지
            def score(item):
                t = item.get("title") or item.get("name") or ""
                return _title_similarity(query, t)
            best = max(candidates, key=score)
            if score(best) > 0.3:  # 최소 유사도 임계값
                return best
        except Exception as e:
            logger.debug("TMDB search 오류: %s", e)
    return None


def _tmdb_movie_detail(tmdb_id: int) -> Optional[dict]:
    """TMDB 영화 상세 (cast + 한국 개봉일 + 한국 등급)"""
    if not _tmdb_available():
        return None
    try:
        r = requests.get(
            f"{_TMDB_URL}/movie/{tmdb_id}",
            params=_tmdb_params({"language": "ko-KR",
                                  "append_to_response": "credits,release_dates"}),
            headers=_tmdb_headers(), timeout=REQUEST_TIMEOUT,
        )
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.debug("TMDB movie detail 오류: %s", e)
        return None


def _tmdb_tv_detail(tmdb_id: int) -> Optional[dict]:
    """TMDB TV 드라마 상세 (cast + 첫방영일 + 한국 등급)"""
    if not _tmdb_available():
        return None
    try:
        r = requests.get(
            f"{_TMDB_URL}/tv/{tmdb_id}",
            params=_tmdb_params({"language": "ko-KR",
                                  "append_to_response": "credits,content_ratings"}),
            headers=_tmdb_headers(), timeout=REQUEST_TIMEOUT,
        )
        return r.json() if r.status_code == 200 else None
    except Exception as e:
        logger.debug("TMDB tv detail 오류: %s", e)
        return None


def _tmdb_get_detail(item: dict) -> Optional[dict]:
    """search 결과로 movie/tv 상세 fetch"""
    media = item.get("media_type")
    tid   = item.get("id")
    if media == "movie":
        return _tmdb_movie_detail(tid)
    if media == "tv":
        return _tmdb_tv_detail(tid)
    return None


def _tmdb_director(detail: dict, media_type: str) -> Optional[str]:
    credits = detail.get("credits", {})
    crew    = credits.get("crew", [])
    for m in crew:
        if m.get("job") == "Director":
            name = m.get("name", "").strip()
            if name and validate_director(name):
                return name
    # TV: 연출 크레딧이 없는 경우 created_by 사용
    if media_type == "tv":
        for c in detail.get("created_by", []):
            name = c.get("name", "").strip()
            if name and validate_director(name):
                return name
    return None


def _tmdb_cast(detail: dict) -> List[str]:
    cast_list = detail.get("credits", {}).get("cast", [])
    names = []
    for m in cast_list[:5]:
        name = m.get("name", "").strip()
        if name and validate_director(name):
            names.append(name)
        if len(names) >= 3:
            break
    return names


def _tmdb_rating(detail: dict, media_type: str) -> Optional[str]:
    if media_type == "movie":
        for country in detail.get("release_dates", {}).get("results", []):
            if country.get("iso_3166_1") == "KR":
                for rd in country.get("release_dates", []):
                    cert = rd.get("certification", "").strip()
                    mapped = _TMDB_KR_RATING.get(cert)
                    if mapped and validate_rating(mapped):
                        return mapped
        # US 폴백
        for country in detail.get("release_dates", {}).get("results", []):
            if country.get("iso_3166_1") == "US":
                for rd in country.get("release_dates", []):
                    cert = rd.get("certification", "").strip().upper()
                    mapped = _TMDB_US_RATING.get(cert)
                    if mapped and validate_rating(mapped):
                        return mapped
    else:  # tv
        for country in detail.get("content_ratings", {}).get("results", []):
            if country.get("iso_3166_1") == "KR":
                cert = country.get("rating", "").strip()
                mapped = _TMDB_KR_RATING.get(cert)
                if mapped and validate_rating(mapped):
                    return mapped
    return None


def _tmdb_release_date(detail: dict, media_type: str) -> Optional[str]:
    if media_type == "movie":
        # 한국 개봉일 우선
        for country in detail.get("release_dates", {}).get("results", []):
            if country.get("iso_3166_1") == "KR":
                for rd in country.get("release_dates", []):
                    d = rd.get("release_date", "")[:10]
                    if d and validate_date(d):
                        return d
        # 기본 개봉일 폴백
        d = (detail.get("release_date") or "")[:10]
        if d and validate_date(d):
            return d
    else:  # tv
        d = (detail.get("first_air_date") or "")[:10]
        if d and validate_date(d):
            return d
    return None


# ─────────────────────────────────────────
# KMDB 헬퍼
# ─────────────────────────────────────────

def _kmdb_search(title: str) -> Optional[dict]:
    """KMDB API 검색 → 첫 번째 결과 반환"""
    if not KMDB_API_KEY:
        return None
    clean = _strip_episode(title)
    try:
        r = requests.get(
            _KMDB_URL,
            params={
                "ServiceKey": KMDB_API_KEY,
                "collection": "kmdb_new2",
                "title": clean,
                "format": "json",
                "detail": "Y",
                "listCount": 1,
            },
            headers=_HEADERS, timeout=REQUEST_TIMEOUT,
        )
        if r.status_code != 200:
            return None
        data = r.json().get("Data", [])
        if not data:
            return None
        results = data[0].get("Result", [])
        return results[0] if results else None
    except Exception as e:
        logger.debug("KMDB search 오류: %s", e)
        return None


def _kmdb_director(item: dict) -> Optional[str]:
    for d in item.get("directors", {}).get("director", []):
        name = d.get("directorNm", "").strip()
        if name and validate_director(name):
            return name
    return None


def _kmdb_cast(item: dict) -> List[str]:
    names = []
    for a in item.get("actors", {}).get("actor", []):
        name = a.get("actorNm", "").strip()
        if name and validate_director(name):
            names.append(name)
        if len(names) >= 3:
            break
    return names


def _kmdb_rating(item: dict) -> Optional[str]:
    raw = item.get("rating", "").strip()
    # KMDB 등급: "전체관람가", "12세관람가", "15세관람가", "18세관람가", "청소년관람불가"
    _map = {
        "전체관람가": "전체이용가",
        "전체이용가": "전체이용가",
        "12세관람가": "12세이용가",
        "12세이용가": "12세이용가",
        "15세관람가": "15세이용가",
        "15세이용가": "15세이용가",
        "18세관람가": "청소년관람불가",
        "청소년관람불가": "청소년관람불가",
    }
    mapped = _map.get(raw, raw)
    return mapped if validate_rating(mapped) else None


def _kmdb_release_date(item: dict) -> Optional[str]:
    raw = item.get("repRlsDate", "").strip()  # YYYYMMDD
    if len(raw) == 8 and raw.isdigit():
        candidate = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        if validate_date(candidate):
            return candidate
    return None


# ─────────────────────────────────────────
# AI-Hub 헬퍼 (로컬 JSON 데이터셋)
# ─────────────────────────────────────────

_aihub_data: Optional[list] = None

def _aihub_load() -> list:
    """AI-Hub 문화콘텐츠 스토리 데이터 로컬 파일 로드 (최초 1회)"""
    global _aihub_data
    if _aihub_data is not None:
        return _aihub_data
    if not _AIHUB_PATH.exists():
        logger.debug("AI-Hub 데이터 파일 없음: %s", _AIHUB_PATH)
        _aihub_data = []
        return _aihub_data
    try:
        with open(_AIHUB_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        # 형식이 리스트인지 dict인지 유연하게 처리
        _aihub_data = raw if isinstance(raw, list) else raw.get("data", [])
        logger.info("AI-Hub 데이터 %d건 로드 완료", len(_aihub_data))
    except Exception as e:
        logger.debug("AI-Hub 로드 오류: %s", e)
        _aihub_data = []
    return _aihub_data


def _aihub_search(title: str) -> Optional[dict]:
    """타이틀로 AI-Hub 데이터 로컬 검색 (정확 → 부분 매치)"""
    data = _aihub_load()
    if not data:
        return None
    clean = _strip_episode(title)
    # 정확 매치 우선
    for item in data:
        t = item.get("title", item.get("제목", ""))
        if t == clean or t == title:
            return item
    # 부분 매치
    for item in data:
        t = item.get("title", item.get("제목", ""))
        if clean and clean in t:
            return item
    return None


def _aihub_director(item: dict) -> Optional[str]:
    name = item.get("director", item.get("감독", "")).strip()
    return name if name and validate_director(name) else None


def _aihub_cast(item: dict) -> List[str]:
    raw = item.get("cast", item.get("출연", item.get("배우", "")))
    if isinstance(raw, list):
        names = [n.strip() for n in raw if validate_director(n.strip())]
    elif isinstance(raw, str):
        names = [n.strip() for n in re.split(r"[,，、]", raw)
                 if n.strip() and validate_director(n.strip())]
    else:
        names = []
    return names[:3]


def _aihub_rating(item: dict) -> Optional[str]:
    raw = item.get("rating", item.get("등급", item.get("관람등급", ""))).strip()
    return raw if validate_rating(raw) else None


def _aihub_release_date(item: dict) -> Optional[str]:
    raw = str(item.get("release_date", item.get("개봉일", item.get("방영일", "")))).strip()
    # YYYY-MM-DD or YYYYMMDD
    if re.match(r"\d{4}-\d{2}-\d{2}", raw) and validate_date(raw[:10]):
        return raw[:10]
    if re.match(r"\d{8}$", raw):
        candidate = f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
        if validate_date(candidate):
            return candidate
    return None


# ─────────────────────────────────────────
# Ollama 폴백
# ─────────────────────────────────────────

def _ollama_available() -> bool:
    try:
        return requests.get(f"{OLLAMA_HOST}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


def _ollama_extract(prompt: str) -> Optional[str]:
    if not _ollama_available():
        return None
    try:
        r = requests.post(
            f"{OLLAMA_HOST}/api/generate",
            json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.1, "num_predict": 64}},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json().get("response", "").strip()
    except Exception as e:
        logger.debug("Ollama 오류: %s", e)
    return None


# ─────────────────────────────────────────
# 공개 검색 함수
# ─────────────────────────────────────────

@_cached
def search_director(asset_nm: str) -> Optional[str]:
    """감독 검색: TMDB → KMDB → AI-Hub → Ollama"""
    # 1. TMDB
    item = _tmdb_search(asset_nm)
    if item:
        detail = _tmdb_get_detail(item)
        if detail:
            name = _tmdb_director(detail, item["media_type"])
            if name:
                logger.info("[director] %s → %s (TMDB)", asset_nm, name)
                return name

    # 2. KMDB
    kmdb = _kmdb_search(asset_nm)
    if kmdb:
        name = _kmdb_director(kmdb)
        if name:
            logger.info("[director] %s → %s (KMDB)", asset_nm, name)
            return name

    # 3. AI-Hub
    aihub = _aihub_search(asset_nm)
    if aihub:
        name = _aihub_director(aihub)
        if name:
            logger.info("[director] %s → %s (AI-Hub)", asset_nm, name)
            return name

    # 4. Ollama LLM
    clean = _strip_episode(asset_nm)
    ans = _ollama_extract(
        f'"{clean}"의 감독 이름만 한 줄로 답해줘 (예: 봉준호). 모르면 "없음".'
    )
    if ans and ans != "없음" and validate_director(ans):
        logger.info("[director] %s → %s (Ollama)", asset_nm, ans)
        return ans

    logger.warning("[director] %s → 검색 실패", asset_nm)
    return None


@_cached
def search_cast_lead(asset_nm: str, genre: str = "") -> List[str]:
    """주연배우 검색 (최대 3명): TMDB → KMDB → AI-Hub → Ollama"""
    # 1. TMDB
    item = _tmdb_search(asset_nm)
    if item:
        detail = _tmdb_get_detail(item)
        if detail:
            cast = _tmdb_cast(detail)
            if cast:
                logger.info("[cast_lead] %s → %s (TMDB)", asset_nm, cast)
                return cast

    # 2. KMDB
    kmdb = _kmdb_search(asset_nm)
    if kmdb:
        cast = _kmdb_cast(kmdb)
        if cast:
            logger.info("[cast_lead] %s → %s (KMDB)", asset_nm, cast)
            return cast

    # 3. AI-Hub
    aihub = _aihub_search(asset_nm)
    if aihub:
        cast = _aihub_cast(aihub)
        if cast:
            logger.info("[cast_lead] %s → %s (AI-Hub)", asset_nm, cast)
            return cast

    # 4. Ollama
    clean = _strip_episode(asset_nm)
    ans = _ollama_extract(
        f'"{clean}"의 주연배우 이름을 최대 3명, 쉼표로 구분해서 답해줘. 모르면 "없음".'
    )
    if ans and ans != "없음":
        names = [n.strip() for n in ans.split(",") if validate_director(n.strip())]
        if names:
            logger.info("[cast_lead] %s → %s (Ollama)", asset_nm, names)
            return names[:3]

    logger.warning("[cast_lead] %s → 검색 실패", asset_nm)
    return []


@_cached
def search_rating(asset_nm: str) -> Optional[str]:
    """연령등급 검색: TMDB → KMDB → AI-Hub"""
    # 1. TMDB
    item = _tmdb_search(asset_nm)
    if item:
        detail = _tmdb_get_detail(item)
        if detail:
            rating = _tmdb_rating(detail, item["media_type"])
            if rating:
                logger.info("[rating] %s → %s (TMDB)", asset_nm, rating)
                return rating

    # 2. KMDB
    kmdb = _kmdb_search(asset_nm)
    if kmdb:
        rating = _kmdb_rating(kmdb)
        if rating:
            logger.info("[rating] %s → %s (KMDB)", asset_nm, rating)
            return rating

    # 3. AI-Hub
    aihub = _aihub_search(asset_nm)
    if aihub:
        rating = _aihub_rating(aihub)
        if rating:
            logger.info("[rating] %s → %s (AI-Hub)", asset_nm, rating)
            return rating

    logger.warning("[rating] %s → 검색 실패", asset_nm)
    return None


@_cached
def search_release_date(asset_nm: str) -> Optional[str]:
    """개봉/방영일 검색: TMDB → KMDB → AI-Hub"""
    # 1. TMDB
    item = _tmdb_search(asset_nm)
    if item:
        detail = _tmdb_get_detail(item)
        if detail:
            date = _tmdb_release_date(detail, item["media_type"])
            if date:
                logger.info("[release_date] %s → %s (TMDB)", asset_nm, date)
                return date

    # 2. KMDB
    kmdb = _kmdb_search(asset_nm)
    if kmdb:
        date = _kmdb_release_date(kmdb)
        if date:
            logger.info("[release_date] %s → %s (KMDB)", asset_nm, date)
            return date

    # 3. AI-Hub
    aihub = _aihub_search(asset_nm)
    if aihub:
        date = _aihub_release_date(aihub)
        if date:
            logger.info("[release_date] %s → %s (AI-Hub)", asset_nm, date)
            return date

    logger.warning("[release_date] %s → 검색 실패", asset_nm)
    return None
