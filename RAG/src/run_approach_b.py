"""
PLAN_00b Step 3 v8: 접근법 B — ct_cl 분기 + 시리즈 캐시 + TMDB/KMDB/JW/DATA_GO
                     + ThreadPoolExecutor 병렬처리

아키텍처:
  ThreadPoolExecutor(MAX_WORKERS) → process_one 병렬 실행
  SeriesCache (thread-safe, Condition variable) → 동일 시리즈 중복 fetch 방지
  폴백 체인: TMDB → (KMDB ‖ JustWatch 병렬) → DATA_GO 순차
  API별 BoundedSemaphore: TMDB=8, JW=5, KMDB=3, DATA_GO=3
"""
import sys
import os
import re
import csv
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, List, Dict, Any, Callable

import requests
import xml.etree.ElementTree as ET
from dotenv import load_dotenv
from tqdm import tqdm

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
load_dotenv(ROOT / "RAG" / "config" / "api_keys.env", override=False)

INPUT_CSV   = ROOT / "RAG" / "data" / "comparison_sample.csv"
OUTPUT_JSON = ROOT / "RAG" / "reports" / "result_B.json"

sys.path.insert(0, str(ROOT / "RAG" / "src"))
from validation import validate_cast, validate_rating, validate_date, validate_director

TMDB_API_KEY           = os.getenv("TMDB_API_KEY", "")
TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN", "")
KMDB_API_KEY           = os.getenv("KMDB_API_KEY", "")
DATA_GO_API_KEY        = os.getenv("DATA_GO_API_KEY", "")
# ── 병렬처리 설정 (조정 가능) ──────────────────────
MAX_WORKERS       = 30   # 동시 처리 건 수
SEM_TMDB_COUNT    = 12    # TMDB ~40 req/s 한도 내
SEM_JW_COUNT      = 8    # JustWatch (비공개 한도)
SEM_KMDB_COUNT    = 3    # 공공 API 보수적
SEM_DATA_GO_COUNT = 3    # 공공 API 보수적

_sem_tmdb    = threading.BoundedSemaphore(SEM_TMDB_COUNT)
_sem_jw      = threading.BoundedSemaphore(SEM_JW_COUNT)
_sem_kmdb    = threading.BoundedSemaphore(SEM_KMDB_COUNT)
_sem_data_go = threading.BoundedSemaphore(SEM_DATA_GO_COUNT)
# ────────────────────────────────────────────────────

REQUEST_TIMEOUT        = 8
_TMDB_URL              = "https://api.themoviedb.org/3"
_KMDB_URL              = "http://api.koreafilm.or.kr/openapi-data2/wisenut/search_api/search_json2.jsp"
_DATA_GO_RATING_URL    = "https://apis.data.go.kr/B551008/video_v2/video_search_v2"
_JW_GRAPHQL_URL        = "https://apis.justwatch.com/graphql"
_HEADERS               = {"User-Agent": "vod-rag-pipeline/1.0"}
_JW_HEADERS            = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
}

# ct_cl → TMDB media_type 힌트
_MOVIE_TYPES  = {"영화"}
_VARIETY_TYPES = {"TV 연예/오락"}  # 에피소드 레벨 게스트 필요

# TMDB 한국 등급 → VALID_RATINGS 기준 표준
_KR_RATING_MAP = {
    "ALL": "전체관람가",
    "7":   "7세이상관람가",
    "12":  "12세이상관람가",
    "14":  "14세이상관람가",
    "15":  "15세이상관람가",
    "18":  "18세이상관람가",
    "19":  "청소년관람불가",
}
# KMDB 등급 (이미 표준 형식)
_KMDB_VALID_RATINGS = {
    "전체관람가", "12세이상관람가", "15세이상관람가",
    "18세이상관람가", "청소년관람불가",
}
# KMDB 반환값 → validation 표준 등급 변환
# 출처: 영화상세정보API.txt 출력값 21번 rating 샘플
_KMDB_RATING_MAP = {
    "전체관람가":   "전체관람가",
    "12세관람가":   "12세이상관람가",
    "15세관람가":   "15세이상관람가",
    "18세관람가":   "18세이상관람가",
    "청소년관람불가": "청소년관람불가",
}

# ─────────────────────────────────────────
# 국가별 등급 → 한국 등급 변환 테이블
# 출처: 나무위키 영상물 등급 제도 비교표
# ─────────────────────────────────────────
_INTL_RATING_TO_KR: dict = {
    # 미국 MPAA
    ("US", "G"):      "전체관람가",
    ("US", "PG"):     "전체관람가",
    ("US", "PG-13"):  "12세이상관람가",
    ("US", "R"):      "청소년관람불가",
    ("US", "NC-17"):  "청소년관람불가",
    # 일본
    ("JP", "G"):      "전체관람가",
    ("JP", "PG12"):   "12세이상관람가",
    ("JP", "R15+"):   "15세이상관람가",
    ("JP", "R18+"):   "청소년관람불가",
    # 영국 BBFC
    ("GB", "U"):      "전체관람가",
    ("GB", "PG"):     "전체관람가",
    ("GB", "12A"):    "12세이상관람가",
    ("GB", "12"):     "12세이상관람가",
    ("GB", "15"):     "15세이상관람가",
    ("GB", "18"):     "청소년관람불가",
    ("GB", "R18"):    "청소년관람불가",
    # 호주 ACB
    ("AU", "G"):      "전체관람가",
    ("AU", "PG"):     "전체관람가",
    ("AU", "M"):      "12세이상관람가",
    ("AU", "MA15+"):  "15세이상관람가",
    ("AU", "R18+"):   "청소년관람불가",
    ("AU", "X18+"):   "청소년관람불가",
    # 대만
    ("TW", "0+"):     "전체관람가",
    ("TW", "6+"):     "전체관람가",
    ("TW", "12+"):    "12세이상관람가",
    ("TW", "15+"):    "15세이상관람가",
    ("TW", "18+"):    "청소년관람불가",
    # 홍콩
    ("HK", "I"):      "전체관람가",
    ("HK", "IIA"):    "전체관람가",
    ("HK", "IIB"):    "15세이상관람가",
    ("HK", "III"):    "청소년관람불가",
    # 싱가포르
    ("SG", "G"):      "전체관람가",
    ("SG", "PG"):     "전체관람가",
    ("SG", "PG13"):   "12세이상관람가",
    ("SG", "NC16"):   "15세이상관람가",
    ("SG", "M18"):    "청소년관람불가",
    ("SG", "R21"):    "청소년관람불가",
    # 프랑스
    ("FR", "U"):      "전체관람가",
    ("FR", "12"):     "12세이상관람가",
    ("FR", "16"):     "15세이상관람가",
    ("FR", "18"):     "청소년관람불가",
    # 독일 FSK
    ("DE", "0"):      "전체관람가",
    ("DE", "6"):      "전체관람가",
    ("DE", "12"):     "12세이상관람가",
    ("DE", "16"):     "15세이상관람가",
    ("DE", "18"):     "청소년관람불가",
    # 러시아
    ("RU", "0+"):     "전체관람가",
    ("RU", "6+"):     "전체관람가",
    ("RU", "12+"):    "12세이상관람가",
    ("RU", "16+"):    "15세이상관람가",
    ("RU", "18+"):    "청소년관람불가",
    # 베트남
    ("VN", "P"):      "전체관람가",
    ("VN", "C13"):    "12세이상관람가",
    ("VN", "C16"):    "15세이상관람가",
    ("VN", "C18"):    "청소년관람불가",
    # 이탈리아
    ("IT", "T"):      "전체관람가",
    ("IT", "VM14"):   "14세이상관람가",
    ("IT", "VM18"):   "청소년관람불가",
    # 캐나다
    ("CA", "G"):      "전체관람가",
    ("CA", "PG"):     "12세이상관람가",
    ("CA", "14A"):    "15세이상관람가",
    ("CA", "18A"):    "청소년관람불가",
    ("CA", "R"):      "청소년관람불가",
    ("CA", "A"):      "청소년관람불가",
}

# KR 없을 때 시도할 국가 우선순위 (아시아 콘텐츠 고려)
_COUNTRY_PRIORITY = ["JP", "TW", "HK", "SG", "US", "GB", "AU", "FR", "DE", "RU", "VN", "IT", "CA"]

# 방심위 API 등급 코드 → 표준 한국 등급 (코드값과 한글 텍스트 모두 대응)
_DATA_GO_RATING_MAP = {
    # 코드 형식
    "AL":  "전체관람가",
    "7":   "7세이상관람가",
    "12":  "12세이상관람가",
    "15":  "15세이상관람가",
    "19":  "청소년관람불가",
    # 한글 텍스트 형식
    "전체":       "전체관람가",
    "전체관람가":  "전체관람가",
    "7세":        "7세이상관람가",
    "7세이상":     "7세이상관람가",
    "7세이상관람가": "7세이상관람가",
    "12세":       "12세이상관람가",
    "12세이상":    "12세이상관람가",
    "12세이상관람가": "12세이상관람가",
    "15세":       "15세이상관람가",
    "15세이상":    "15세이상관람가",
    "15세이상관람가": "15세이상관람가",
    "19세":       "청소년관람불가",
    "19세이상":    "청소년관람불가",
    "청소년관람불가": "청소년관람불가",
    "청불":        "청소년관람불가",
}

# 에피소드/회차/시즌 번호 제거 패턴
_RE_EPISODE = re.compile(
    r'\s*[\(\[]?(?:\d{1,4}화|제?\d{1,4}회\.?|[Ss]\d{1,2}[Ee]\d{1,3}|'
    r'시즌\s*\d+|Season\s*\d+|\d+기|\d+편)[\)\]]?\s*\.?$',
    re.IGNORECASE,
)
_RE_TRAILING_NUM    = re.compile(r'\s+([1-9]|1[0-9])\s*$')
_RE_TRAILING_PERIOD = re.compile(r'\.\s*$')


# ─────────────────────────────────────────
# 시리즈 캐시
# ─────────────────────────────────────────

_CACHE_PENDING = object()  # sentinel: 다른 스레드가 fetch 중


class SeriesCache:
    """
    시리즈명 → API 조회 결과 캐시 (thread-safe).

    get_or_fetch(key, fn):
      - 캐시 히트 → 즉시 반환
      - 첫 번째 미스 → fn() 실행 후 저장 (이 스레드 담당)
      - 동시 미스  → Condition.wait() 로 첫 번째 fetch 완료까지 대기
                     → 완료 후 결과 재사용 (중복 API 호출 0)
    """
    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._cond  = threading.Condition(threading.Lock())
        self.hits   = 0
        self.misses = 0

    def get_or_fetch(self, key: str, fetch_fn: Callable[[], dict]) -> dict:
        with self._cond:
            val = self._data.get(key, None)
            if val is not None and val is not _CACHE_PENDING:
                self.hits += 1
                return val
            if val is _CACHE_PENDING:
                # 다른 스레드가 fetch 중 — 완료 대기
                while self._data.get(key) is _CACHE_PENDING:
                    self._cond.wait()
                self.hits += 1
                return self._data[key]
            # 첫 번째 미스: 이 스레드가 fetch 담당
            self.misses += 1
            self._data[key] = _CACHE_PENDING

        # Lock 해제 상태에서 HTTP 실행
        try:
            result = fetch_fn()
        except Exception:
            result = {
                "tmdb_id": None, "media_type": None, "cast_lead": None,
                "director": None, "release_date": None, "rating": None,
                "smry": None, "series_nm": None, "disp_rtm": None, "source": None,
            }
        finally:
            with self._cond:
                self._data[key] = result
                self._cond.notify_all()

        return result

    def stats(self) -> str:
        total = self.hits + self.misses
        return f"캐시 히트 {self.hits}/{total}건 ({self.hits/total*100:.0f}%)" if total else ""


_cache = SeriesCache()


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────

def _series_name(title: str) -> str:
    """에피소드·시즌·회차 전부 제거 → 시리즈 캐시 키."""
    prev, t = None, title.strip()
    while t != prev:
        prev = t
        t = _RE_EPISODE.sub("", t).strip()
    t = _RE_TRAILING_NUM.sub("", t).strip()
    t = _RE_TRAILING_PERIOD.sub("", t).strip()  # 회차 뒤 마침표 제거
    return t if t else title.strip()


def _ko_single_space_variants(s: str) -> list:
    """한글-한글 경계마다 공백을 하나씩 삽입한 변형 목록.
    예: 명탐정코난 → ['명 탐정코난', '명탐 정코난', '명탐정 코난', '명탐정코 난']
    TMDB 검색 API가 공백 없는 한글을 인식 못할 때 대안 쿼리로 사용.
    """
    variants = []
    for i in range(1, len(s)):
        if '\uAC00' <= s[i - 1] <= '\uD7A3' and '\uAC00' <= s[i] <= '\uD7A3':
            variants.append(s[:i] + ' ' + s[i:])
    return variants


def _build_queries(series: str, original: str) -> list:
    """검색 쿼리 변형 목록 (중복 제거, 순서 유지)."""
    # 숫자-한글 사이 공백
    spaced = re.sub(r'([가-힣A-Za-z])(\d)', r'\1 \2', series)
    # 서브제목 제거: ': X', '- X', ' with X'
    no_sub = re.split(r'\s*(?:[:\-]|with\s)', series, maxsplit=1)[0].strip()
    # 한글 붙여쓰기 → 단일 공백 삽입 변형 (TMDB가 공백 없는 한글을 못 찾을 때)
    space_variants = _ko_single_space_variants(series)
    base = [series, spaced, no_sub] + space_variants + [original]
    return list(dict.fromkeys(q for q in base if q))


def _title_similarity(a: str, b: str) -> float:
    # 공백 제거 후 비교: 붙여쓰기 타이틀과 TMDB 결과 간 공백 차이 무시
    a, b = a.lower().strip().replace(' ', ''), b.lower().strip().replace(' ', '')
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    len_ratio = min(len(a), len(b)) / max(len(a), len(b))
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return len_ratio
    return len(set(a) & set(b)) / max(len(set(a)), len(set(b))) * len_ratio


# ─────────────────────────────────────────
# TMDB API
# ─────────────────────────────────────────

def _tmdb_headers() -> dict:
    h = dict(_HEADERS)
    if TMDB_READ_ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {TMDB_READ_ACCESS_TOKEN}"
    return h


def _tmdb_params(extra: dict = None) -> dict:
    p = dict(extra or {})
    if not TMDB_READ_ACCESS_TOKEN and TMDB_API_KEY:
        p["api_key"] = TMDB_API_KEY
    return p


def _tmdb_search(series: str, original: str, prefer_movie: bool = False) -> Optional[dict]:
    """TMDB search/multi → 최고 유사도 결과. ko-KR → en-US 순."""
    want_type = "movie" if prefer_movie else "tv"
    for lang in ["ko-KR", "en-US"]:
        for query in _build_queries(series, original):
            try:
                with _sem_tmdb:
                    r = requests.get(
                        f"{_TMDB_URL}/search/multi",
                        params=_tmdb_params({"query": query, "language": lang, "page": 1}),
                        headers=_tmdb_headers(),
                        timeout=REQUEST_TIMEOUT,
                    )
                results = r.json().get("results", [])

                # 원하는 타입 우선, 없으면 다른 타입도 허용
                candidates = [i for i in results if i.get("media_type") == want_type]
                if not candidates:
                    candidates = [i for i in results if i.get("media_type") in ("movie", "tv")]
                if not candidates:
                    continue

                def _sim(item: dict) -> float:
                    names = [
                        item.get("title") or "", item.get("name") or "",
                        item.get("original_title") or "", item.get("original_name") or "",
                    ]
                    return max((_title_similarity(query, n) for n in names if n), default=0.0)

                best = max(candidates, key=_sim)
                if _sim(best) > 0.3:
                    return best
            except Exception:
                continue
    return None


def _tmdb_series_detail(item: dict) -> Optional[dict]:
    """시리즈/영화 상세 정보 (credits + 등급) fetch."""
    media_type = item["media_type"]
    item_id    = item["id"]
    try:
        if media_type == "movie":
            with _sem_tmdb:
                r = requests.get(
                    f"{_TMDB_URL}/movie/{item_id}",
                    params=_tmdb_params({
                        "language": "ko-KR",
                        "append_to_response": "credits,release_dates",
                    }),
                    headers=_tmdb_headers(), timeout=REQUEST_TIMEOUT,
                )
        else:
            with _sem_tmdb:
                r = requests.get(
                    f"{_TMDB_URL}/tv/{item_id}",
                    params=_tmdb_params({
                        "language": "ko-KR",
                        "append_to_response": "credits,content_ratings",
                    }),
                    headers=_tmdb_headers(), timeout=REQUEST_TIMEOUT,
                )
        detail = r.json()
        detail["_media_type"] = media_type

        # TV: episode_run_time 비어 있으면 시즌1 에피소드에서 런타임 추출
        if media_type == "tv" and not detail.get("episode_run_time"):
            try:
                with _sem_tmdb:
                    sr = requests.get(
                        f"{_TMDB_URL}/tv/{item_id}/season/1",
                        params=_tmdb_params({"language": "ko-KR"}),
                        headers=_tmdb_headers(), timeout=REQUEST_TIMEOUT,
                    )
                for ep in sr.json().get("episodes", [])[:5]:
                    rt = ep.get("runtime")
                    if isinstance(rt, int) and rt > 0:
                        detail["_ep_runtime_fallback"] = rt
                        break
            except Exception:
                pass

        return detail
    except Exception:
        return None


# ─────────────────────────────────────────
# 필드 추출
# ─────────────────────────────────────────

def _extract_smry(detail: dict) -> Optional[str]:
    """TMDB overview → smry. 한국어(ko-KR) 우선, 10자 이상만 허용."""
    overview = (detail.get("overview") or "").strip()
    return overview if len(overview) >= 10 else None


def _extract_series_nm(detail: dict) -> Optional[str]:
    """TMDB name/title → series_nm."""
    media_type = detail.get("_media_type", "movie")
    name = (detail.get("name") or detail.get("title") or "").strip()
    return name if name else None


def _extract_disp_rtm(detail: dict) -> Optional[str]:
    """TMDB runtime(분) → 'HH:MM' 형식 문자열.
    영화: runtime(int), TV: episode_run_time → 시즌1 에피소드 폴백 순."""
    media_type = detail.get("_media_type", "movie")
    if media_type == "movie":
        minutes = detail.get("runtime")
    else:
        rts = detail.get("episode_run_time", [])
        minutes = rts[0] if rts else detail.get("_ep_runtime_fallback")
    if not minutes or not isinstance(minutes, int) or minutes <= 0:
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _extract_cast(detail: dict) -> Optional[List[str]]:
    cast = [c["name"] for c in detail.get("credits", {}).get("cast", [])[:4]]
    valid = [n for n in cast if validate_director(n)]
    return valid if valid else None


def _extract_director(detail: dict) -> Optional[str]:
    media_type = detail.get("_media_type", "movie")
    crew = detail.get("credits", {}).get("crew", [])
    jobs = ["Director"] if media_type == "movie" else ["Series Director", "Director", "Executive Producer"]
    for job in jobs:
        for c in crew:
            if c.get("job") == job and validate_director(c.get("name", "")):
                return c["name"]
    # TV: created_by 폴백
    if media_type == "tv":
        for creator in detail.get("created_by", []):
            name = creator.get("name", "")
            if name and validate_director(name):
                return name
    return None


def _extract_release_date(detail: dict) -> Optional[str]:
    media_type = detail.get("_media_type", "movie")
    date_str = detail.get("release_date" if media_type == "movie" else "first_air_date", "")
    return date_str if date_str and validate_date(date_str) else None


def _map_kr_cert(cert: str) -> Optional[str]:
    """KR 등급 코드 → 표준 한국 등급 문자열. 숫자 코드 자동 생성 포함."""
    mapped = _KR_RATING_MAP.get(cert)
    if mapped is None:
        if cert.isdigit() and 1 <= int(cert) <= 25:
            mapped = f"{cert}세이상관람가"
            from validation import VALID_RATINGS
            VALID_RATINGS.add(mapped)
        else:
            mapped = cert
    return mapped if validate_rating(mapped) else None


def _extract_rating(detail: dict) -> Optional[str]:
    media_type = detail.get("_media_type", "movie")

    if media_type == "movie":
        all_certs: dict = {}
        for entry in detail.get("release_dates", {}).get("results", []):
            iso = entry.get("iso_3166_1", "")
            for rd in entry.get("release_dates", []):
                c = rd.get("certification", "")
                if c and iso not in all_certs:
                    all_certs[iso] = c
    else:
        all_certs = {}
        for entry in detail.get("content_ratings", {}).get("results", []):
            iso = entry.get("iso_3166_1", "")
            c   = entry.get("rating", "")
            if c and iso not in all_certs:
                all_certs[iso] = c

    # 1순위: KR 직접 매핑
    if "KR" in all_certs:
        result = _map_kr_cert(all_certs["KR"])
        if result:
            return result

    # 2순위: 국가별 변환 테이블
    for country in _COUNTRY_PRIORITY:
        if country in all_certs:
            kr = _INTL_RATING_TO_KR.get((country, all_certs[country]))
            if kr and validate_rating(kr):
                return kr

    return None


# ─────────────────────────────────────────
# KMDB 폴백 (한국 콘텐츠 전용)
# ─────────────────────────────────────────

def _kmdb_search(series: str) -> Optional[dict]:
    if not KMDB_API_KEY:
        return None
    try:
        with _sem_kmdb:
            r = requests.get(
                _KMDB_URL,
                params={
                    "collection": "kmdb_new2", "query": series,
                    "detail": "Y", "ServiceKey": KMDB_API_KEY, "listCount": 3,
                },
                headers=_HEADERS, timeout=REQUEST_TIMEOUT,
            )
        items = (r.json().get("Data") or [{}])[0].get("Result") or []
        if not items:
            return None
        item = items[0]
        kmdb_title = item.get("title", "").replace("!HS", "").replace("!HE", "").strip()
        return item if _title_similarity(series, kmdb_title) > 0.3 else None
    except Exception:
        return None


def _parse_kmdb(item: dict) -> dict:
    out = {}
    directors = item.get("directors", {}).get("director", [])
    if directors:
        name = directors[0].get("directorNm", "").strip()
        if name and validate_director(name):
            out["director"] = name
    actors = item.get("actors", {}).get("actor", [])
    names = [a.get("actorNm", "").strip() for a in actors[:5] if a.get("actorNm")]
    valid = [n for n in names if validate_director(n)]
    if valid:
        out["cast_lead"] = valid[:3]
    rd = item.get("repRlsDate", "").strip().replace(" ", "")
    if re.match(r'^\d{8}$', rd):
        date_str = f"{rd[:4]}-{rd[4:6]}-{rd[6:]}"
        if validate_date(date_str):
            out["release_date"] = date_str
    rating_raw = item.get("rating", "").strip()
    mapped_rating = _KMDB_RATING_MAP.get(rating_raw, rating_raw)
    if mapped_rating in _KMDB_VALID_RATINGS:
        out["rating"] = mapped_rating
    # KMDB runtime → disp_rtm (분 단위 숫자 문자열)
    runtime_raw = item.get("runtime", "").strip()
    if runtime_raw:
        try:
            if runtime_raw.isdigit():
                mins = int(runtime_raw)
            elif ":" in runtime_raw:
                h, m = runtime_raw.split(":", 1)
                mins = int(h) * 60 + int(m)
            else:
                m = re.search(r'\d+', runtime_raw)
                mins = int(m.group()) if m else 0
            if 1 <= mins <= 300:
                out["disp_rtm"] = f"{mins // 60:02d}:{mins % 60:02d}"
        except Exception:
            pass
    return out


# ─────────────────────────────────────────
# JustWatch GraphQL 폴백 (TV 시리즈 rating·runtime·cast·director 보완)
# ─────────────────────────────────────────

_JW_QUERY = """
query SearchTitles($q: String!, $country: Country!, $lang: Language!) {
  popularTitles(country: $country, filter: { searchQuery: $q }) {
    edges {
      node {
        objectType
        content(country: $country, language: $lang) {
          title
          runtime
          ageCertification
          shortDescription
          credits { role name }
        }
      }
    }
  }
}
"""

# JustWatch ageCertification → 표준 한국 등급
# KR 로케일 반환값: "ALL", "7", "12", "15", "18", "19"
_JW_CERT_MAP = {
    "ALL": "전체관람가",
    "7":   "7세이상관람가",
    "12":  "12세이상관람가",
    "15":  "15세이상관람가",
    "18":  "18세이상관람가",
    "19":  "청소년관람불가",
}


def _jw_search(series: str, original: str) -> dict:
    """JustWatch GraphQL API로 메타데이터 조회.
    반환: {rating, disp_rtm, director, cast_lead, smry} — 확보된 필드만 포함.

    - TV 시리즈 rating: TMDB content_ratings 미등록 케이스 보완 핵심 소스
    - 유사도 임계값 0.5 (JustWatch 검색 정확도 높음)
    - cast/director: 영문 로마자 표기 반환 가능
    """
    out: dict = {}
    try:
        with _sem_jw:
            r = requests.post(
                _JW_GRAPHQL_URL,
                json={
                    "query": _JW_QUERY,
                    "variables": {"q": series, "country": "KR", "lang": "ko"},
                },
                headers=_JW_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
        if r.status_code != 200:
            return out
        edges = r.json().get("data", {}).get("popularTitles", {}).get("edges", [])
        if not edges:
            return out

        for edge in edges[:3]:
            content = edge["node"].get("content", {})
            jw_title = (content.get("title") or "").strip()
            if _title_similarity(series, jw_title) < 0.5:
                # 원본 타이틀로도 재시도
                if _title_similarity(original, jw_title) < 0.5:
                    continue

            # 등급 (ageCertification)
            cert = (content.get("ageCertification") or "").strip().upper()
            if cert:
                mapped = _JW_CERT_MAP.get(cert)
                if mapped and validate_rating(mapped):
                    out["rating"] = mapped

            # 상영/방영 시간 (runtime — 분 단위 int)
            rt = content.get("runtime")
            if isinstance(rt, int) and 1 <= rt <= 300:
                out["disp_rtm"] = f"{rt // 60:02d}:{rt % 60:02d}"

            # 감독 (DIRECTOR role)
            credits = content.get("credits", [])
            for c in credits:
                if c.get("role") == "DIRECTOR":
                    name = (c.get("name") or "").strip()
                    if name and validate_director(name):
                        out["director"] = name
                        break

            # 주연 (ACTOR role — 상위 4명)
            actors = [
                c["name"].strip() for c in credits
                if c.get("role") == "ACTOR" and c.get("name")
            ]
            valid_actors = [n for n in actors if validate_director(n)]
            if valid_actors:
                out["cast_lead"] = valid_actors[:4]

            # 줄거리 (shortDescription)
            smry = (content.get("shortDescription") or "").strip()
            if len(smry) >= 10:
                out["smry"] = smry

            if out:
                break
    except Exception:
        pass
    return out


# ─────────────────────────────────────────
# 방심위 DATA.GO.KR 폴백 (TV 시리즈 등급 전용)
# ─────────────────────────────────────────

_RE_SCRE_TIME = re.compile(r'(\d+)분\s*(\d*)초?')


def _parse_scre_time(scre: str) -> Optional[str]:
    """'82분 44초' / '56분 초' 형식 → 'HH:MM'."""
    m = _RE_SCRE_TIME.search(scre)
    if not m:
        return None
    mins = int(m.group(1))
    if not (1 <= mins <= 300):
        return None
    return f"{mins // 60:02d}:{mins % 60:02d}"


def _data_go_search(series: str) -> dict:
    """영상물등급위원회 API(B551008/video_v2/video_search_v2) 조회.
    반환: {rating, disp_rtm, director, cast_lead} — 확보된 필드만 포함.

    응답: XML (resultCode 00=정상, items/item 반복)
    핵심 필드: gradeName(등급), screTime(상영시간), direName(감독),
               leadaName(주연), useTitle/oriTitle(제목 매칭용)
    유사도 임계값 0.65 — 부분 매칭으로 인한 성인물 오매칭 방지.
    """
    out: dict = {}
    if not DATA_GO_API_KEY:
        return out
    try:
        with _sem_data_go:
            r = requests.get(
                _DATA_GO_RATING_URL,
                params={
                    "serviceKey": DATA_GO_API_KEY,
                    "pageNo":     "1",
                    "numOfRows":  "10",
                    "title":      series,
                },
                headers=_HEADERS,
                timeout=REQUEST_TIMEOUT,
            )
        if r.status_code != 200:
            return out

        root = ET.fromstring(r.text)
        if root.findtext(".//resultCode", "") != "00":
            return out

        for item in root.findall(".//item"):
            def _t(tag: str) -> str:
                return (item.findtext(tag) or "").strip()

            # 제목 유사도 — 0.80 이상만 허용 (부분 매칭 오염 방지)
            use_title = _t("useTitle") or _t("oriTitle")
            if _title_similarity(series, use_title) < 0.80:
                continue

            # 등급 (gradeName — 이미 표준 한국 등급 형식)
            grade_raw = _t("gradeName")
            if grade_raw:
                mapped = _DATA_GO_RATING_MAP.get(grade_raw, grade_raw)
                if validate_rating(mapped):
                    out["rating"] = mapped

            # 상영시간 (screTime — "82분 44초" 형식)
            rtm = _parse_scre_time(_t("screTime"))
            if rtm:
                out["disp_rtm"] = rtm

            # 감독 (direName)
            dire = _t("direName")
            if dire and validate_director(dire):
                out["director"] = dire

            # 주연 (leadaName — 쉼표 구분 가능)
            leada = _t("leadaName")
            if leada:
                names = [n.strip() for n in re.split(r'[,，/]', leada) if n.strip()]
                valid = [n for n in names if validate_director(n)]
                if valid:
                    out["cast_lead"] = valid[:4]

            if out:   # 첫 매칭 건 확보 시 종료
                break
    except Exception:
        pass
    return out


# ─────────────────────────────────────────
# 시리즈 레벨 TMDB 조회 (캐시 포함)
# ─────────────────────────────────────────

def _fetch_series_data(series: str, original: str, ct_cl: str) -> dict:
    """
    시리즈명으로 TMDB 조회 → 캐시 저장/반환 (thread-safe).
    폴백 체인: TMDB → (KMDB ‖ JustWatch 병렬) → DATA_GO
    """
    def _do_fetch() -> dict:
        prefer_movie = ct_cl in _MOVIE_TYPES
        item = _tmdb_search(series, original, prefer_movie)

        result: Dict[str, Any] = {
            "tmdb_id": None, "media_type": None,
            "cast_lead": None, "director": None,
            "release_date": None, "rating": None,
            "smry": None, "series_nm": None, "disp_rtm": None,
            "source": None,
        }

        if item:
            detail = _tmdb_series_detail(item)
            if detail:
                result["tmdb_id"]      = item["id"]
                result["media_type"]   = item["media_type"]
                result["cast_lead"]    = _extract_cast(detail)
                result["director"]     = _extract_director(detail)
                result["release_date"] = _extract_release_date(detail)
                result["rating"]       = _extract_rating(detail)
                result["smry"]         = _extract_smry(detail)
                result["series_nm"]    = _extract_series_nm(detail)
                result["disp_rtm"]     = _extract_disp_rtm(detail)
                result["source"]       = "TMDB"

        # KMDB + JustWatch 병렬 fetch (두 소스가 독립적이므로 동시 실행)
        needs_kmdb = KMDB_API_KEY and (
            not result["tmdb_id"] or not result["cast_lead"]
            or not result["rating"] or not result["disp_rtm"]
        )
        needs_jw = not result["rating"] or not result["disp_rtm"] \
            or not result["director"] or not result["cast_lead"] \
            or not result["smry"]

        kmdb_result: Dict[str, Any] = {}
        jw_result:   Dict[str, Any] = {}

        if needs_kmdb or needs_jw:
            threads = []
            if needs_kmdb:
                def _run_kmdb():
                    ki = _kmdb_search(series)
                    if ki:
                        kmdb_result.update(_parse_kmdb(ki))
                t = threading.Thread(target=_run_kmdb, daemon=True)
                t.start(); threads.append(t)

            if needs_jw:
                def _run_jw():
                    jw_result.update(_jw_search(series, original))
                t = threading.Thread(target=_run_jw, daemon=True)
                t.start(); threads.append(t)

            for t in threads:
                t.join(timeout=REQUEST_TIMEOUT + 2)

        # KMDB 결과 반영
        if kmdb_result:
            for field in ["cast_lead", "director", "release_date", "rating", "disp_rtm"]:
                if not result[field] and kmdb_result.get(field):
                    result[field] = kmdb_result[field]
                    result["source"] = "KMDB" if not result["tmdb_id"] else "TMDB+KMDB"

        # JustWatch 결과 반영
        if jw_result:
            prev_src = result["source"] or "TMDB"
            contributed = False
            for field in ["rating", "disp_rtm", "director", "cast_lead", "smry"]:
                if not result[field] and jw_result.get(field):
                    result[field] = jw_result[field]
                    contributed = True
            if contributed:
                result["source"] = (
                    "JustWatch" if not result["tmdb_id"] else f"{prev_src}+JW"
                )

        # DATA.GO 폴백 — rating/disp_rtm/director/cast_lead 미확보 시
        needs_dg = DATA_GO_API_KEY and (
            not result["rating"] or not result["disp_rtm"]
            or not result["director"] or not result["cast_lead"]
        )
        if needs_dg:
            dg = _data_go_search(series)
            if dg:
                prev_src = result["source"] or "TMDB"
                contributed = False
                for field in ["rating", "disp_rtm", "director", "cast_lead"]:
                    if not result[field] and dg.get(field):
                        result[field] = dg[field]
                        contributed = True
                if contributed:
                    result["source"] = (
                        "DATA_GO" if not result["tmdb_id"]
                        else f"{prev_src}+DATA_GO"
                    )

        return result

    return _cache.get_or_fetch(series, _do_fetch)


# ─────────────────────────────────────────
# 건별 처리
# ─────────────────────────────────────────

def process_one(row: dict) -> dict:
    asset_nm = row["asset_nm"]
    ct_cl    = row.get("ct_cl", "")
    t0 = time.time()

    result = {
        "full_asset_id":       row["full_asset_id"],
        "asset_nm":            asset_nm,
        "ct_cl":               ct_cl,
        "genre":               row.get("genre", ""),
        "cast_lead":           None,
        "rating":              None,
        "release_date":        None,
        "director":            None,
        "smry":                None,
        "series_nm":           None,
        "disp_rtm":            None,
        "cast_lead_source":    None,
        "rating_source":       None,
        "release_date_source": None,
        "director_source":     None,
        "smry_source":         None,
        "series_nm_source":    None,
        "disp_rtm_source":     None,
        "tmdb_id":             None,
        "tmdb_media_type":     None,
        "is_variety":          ct_cl in _VARIETY_TYPES,
        "elapsed_sec":         0.0,
        "error":               None,
    }

    try:
        series = _series_name(asset_nm)
        data   = _fetch_series_data(series, asset_nm, ct_cl)

        result["tmdb_id"]         = data["tmdb_id"]
        result["tmdb_media_type"] = data["media_type"]
        src = data["source"] or "TMDB"

        if data["cast_lead"] and validate_cast(data["cast_lead"]):
            result["cast_lead"]        = json.dumps(data["cast_lead"], ensure_ascii=False)
            result["cast_lead_source"] = src

        if data["director"]:
            result["director"]        = data["director"]
            result["director_source"] = src

        if data["release_date"]:
            result["release_date"]        = data["release_date"]
            result["release_date_source"] = src

        if data["rating"]:
            result["rating"]        = data["rating"]
            result["rating_source"] = src

        if data["smry"]:
            result["smry"]        = data["smry"]
            result["smry_source"] = src

        if data["series_nm"]:
            result["series_nm"]        = data["series_nm"]
            result["series_nm_source"] = src

        if data["disp_rtm"]:
            result["disp_rtm"]        = data["disp_rtm"]
            result["disp_rtm_source"] = src

        # TV 연예/오락: Step 2에서 episode-level guest_stars 추가 예정
        # result["needs_guest_fetch"] = True 로 마킹됨 (is_variety 필드)

    except Exception as e:
        result["error"] = str(e)

    result["elapsed_sec"] = round(time.time() - t0, 2)
    return result


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────

def main():
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    with open(INPUT_CSV, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    n_rows = len(rows)
    print(f"접근법 B v8 (ThreadPoolExecutor={MAX_WORKERS}) 시작: {n_rows}건", flush=True)

    results: List[dict] = [None] * n_rows  # type: ignore

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {executor.submit(process_one, row): i for i, row in enumerate(rows)}
        with tqdm(total=n_rows, unit="건", ncols=80) as pbar:
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    res = future.result()
                except Exception as e:
                    res = {k: None for k in [
                        "full_asset_id", "asset_nm", "ct_cl", "genre",
                        "cast_lead", "rating", "release_date", "director",
                        "smry", "series_nm", "disp_rtm",
                        "cast_lead_source", "rating_source", "release_date_source",
                        "director_source", "smry_source", "series_nm_source",
                        "disp_rtm_source", "tmdb_id", "tmdb_media_type",
                    ]}
                    res["is_variety"] = False
                    res["elapsed_sec"] = 0.0
                    res["error"] = str(e)
                results[idx] = res
                pbar.update(1)

    # 순서 보존된 결과 집계
    n        = len(results)
    cast_ok  = sum(1 for r in results if r["cast_lead"])
    rate_ok  = sum(1 for r in results if r["rating"])
    date_ok  = sum(1 for r in results if r["release_date"])
    dir_ok   = sum(1 for r in results if r["director"])
    smry_ok  = sum(1 for r in results if r["smry"])
    snm_ok   = sum(1 for r in results if r["series_nm"])
    rtm_ok   = sum(1 for r in results if r["disp_rtm"])
    avg_sec  = sum(r["elapsed_sec"] for r in results) / n
    variety  = sum(1 for r in results if r.get("is_variety"))
    errors   = sum(1 for r in results if r.get("error"))

    summary = {
        "approach":            "B_v8",
        "description":         "TMDB 시리즈 캐시 + ct_cl 분기 + KMDB/JW/DATA_GO + ThreadPoolExecutor",
        "total":               n,
        "max_workers":         MAX_WORKERS,
        "cast_lead_found":     cast_ok,
        "rating_found":        rate_ok,
        "release_date_found":  date_ok,
        "director_found":      dir_ok,
        "smry_found":          smry_ok,
        "series_nm_found":     snm_ok,
        "disp_rtm_found":      rtm_ok,
        "cast_lead_rate":      round(cast_ok / n, 3),
        "rating_rate":         round(rate_ok / n, 3),
        "release_date_rate":   round(date_ok / n, 3),
        "director_rate":       round(dir_ok / n, 3),
        "smry_rate":           round(smry_ok / n, 3),
        "series_nm_rate":      round(snm_ok / n, 3),
        "disp_rtm_rate":       round(rtm_ok / n, 3),
        "avg_elapsed_sec":     round(avg_sec, 2),
        "variety_count":       variety,
        "errors":              errors,
        "cache_stats":         _cache.stats(),
    }

    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "results": results}, f,
                  ensure_ascii=False, indent=2)

    print(f"\n=== 접근법 B v8 완료 ===")
    print(f"cast_lead : {cast_ok}/{n} ({cast_ok/n*100:.1f}%)")
    print(f"rating    : {rate_ok}/{n} ({rate_ok/n*100:.1f}%)")
    print(f"release_dt: {date_ok}/{n} ({date_ok/n*100:.1f}%)")
    print(f"director  : {dir_ok}/{n} ({dir_ok/n*100:.1f}%)")
    print(f"smry      : {smry_ok}/{n} ({smry_ok/n*100:.1f}%)")
    print(f"series_nm : {snm_ok}/{n} ({snm_ok/n*100:.1f}%)")
    print(f"disp_rtm  : {rtm_ok}/{n} ({rtm_ok/n*100:.1f}%)")
    print(f"평균 시간  : {avg_sec:.2f}초/건")
    print(f"예능(게스트 Step2 대상): {variety}건")
    print(f"{_cache.stats()}")
    print(f"결과 저장  : {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
