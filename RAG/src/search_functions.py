"""
search_functions.py — 외부 소스 검색 함수 (Wikipedia → IMDB 폴백)
Phase 1 구현 (PLAN_01 2.1절)

검색 전략:
  director     : Wikipedia KO → Wikipedia EN → IMDB
  cast_lead    : IMDB → Wikipedia KO 폴백
  rating       : KMRB(스크래핑) → IMDB 폴백
  release_date : IMDB → Wikipedia KO 폴백
"""
import os
import re
import time
import logging
import functools
import requests
from typing import Optional, List

from validation import VALID_RATINGS, validate_director, validate_cast, validate_rating, validate_date

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# 설정
# ─────────────────────────────────────────

OLLAMA_HOST  = os.getenv('OLLAMA_HOST',  'http://localhost:11434')
OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'exaone3.5:7.8b')
IMDB_API_KEY = os.getenv('IMDB_API_KEY', '')
REQUEST_TIMEOUT = 8

_HEADERS = {'User-Agent': 'vod-rag-pipeline/1.0 (github.com/vod-recommendation)'}

# 인메모리 캐시
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
# Wikipedia 헬퍼
# ─────────────────────────────────────────

def _normalize_query(title: str) -> str:
    """검색어 정규화: 특수문자 제거, 공백 통일"""
    return re.sub(r'[-:·~\u2014\u2013]', ' ', title).strip()


def _wiki_search_title(query: str, lang: str) -> Optional[str]:
    """Wikipedia Search API로 가장 관련성 높은 문서 제목 반환. 정규화 쿼리도 시도."""
    queries = [query, _normalize_query(query)]
    queries = list(dict.fromkeys(queries))  # 중복 제거
    for q in queries:
        try:
            r = requests.get(
                f'https://{lang}.wikipedia.org/w/api.php',
                params={'action': 'query', 'list': 'search', 'srsearch': q,
                        'format': 'json', 'srlimit': 1},
                timeout=REQUEST_TIMEOUT, headers=_HEADERS,
            )
            if r.status_code == 200:
                results = r.json().get('query', {}).get('search', [])
                if results:
                    return results[0]['title']
        except Exception as e:
            logger.debug("Wiki search[%s] 오류: %s", lang, e)
    return None


def _wiki_summary(title: str, lang: str) -> Optional[dict]:
    """Wikipedia REST summary API — 짧은 소개 텍스트 반환"""
    try:
        r = requests.get(
            f'https://{lang}.wikipedia.org/api/rest_v1/page/summary/{requests.utils.quote(title)}',
            timeout=REQUEST_TIMEOUT, headers=_HEADERS,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug("Wiki summary[%s/%s] 오류: %s", lang, title, e)
    return None


def _wiki_intro(title: str, lang: str) -> str:
    """Wikipedia API — 인트로 섹션 전체 텍스트 반환 (summary보다 길어 cast/date 추출에 유리)"""
    try:
        r = requests.get(
            f'https://{lang}.wikipedia.org/w/api.php',
            params={'action': 'query', 'prop': 'extracts', 'exintro': True,
                    'explaintext': True, 'titles': title, 'format': 'json'},
            timeout=REQUEST_TIMEOUT, headers=_HEADERS,
        )
        if r.status_code == 200:
            pages = r.json().get('query', {}).get('pages', {})
            for page in pages.values():
                return page.get('extract', '')
    except Exception as e:
        logger.debug("Wiki intro[%s/%s] 오류: %s", lang, title, e)
    return ''


def _wiki_search_and_intro(query: str, lang: str) -> tuple[Optional[str], str]:
    """검색 → 인트로 텍스트 반환. (title, text) 튜플"""
    title = _wiki_search_title(query, lang)
    if not title:
        return None, ''
    text = _wiki_intro(title, lang)
    return title, text


# ─────────────────────────────────────────
# 추출 헬퍼
# ─────────────────────────────────────────

_KO_PARTICLES = re.compile(r'[과와이가은는을를의도로]$')  # 이름 끝 조사 필터

def _extract_director(text: str) -> Optional[str]:
    """텍스트에서 감독명 추출 (한국어 + 영어)"""
    patterns = [
        # KO: "봉준호의 일곱 번째 장편 영화" — N번째 공백 허용
        (r'([가-힣]{2,5})의\s+\S+\s+번째\s+(?:장편|단편|영화|작품)', 1),
        (r'([가-힣]{2,5})의\s+\S+번째\s+(?:장편|단편|영화|작품)', 1),
        (r'([가-힣]{2,5})의\s+(?:첫|두|세|네|다섯|여섯|일곱|여덟|아홉|열)\s*번째', 1),
        # KO: "가이 리치가 감독" / "루소가 감독" — 조사(가/이)가 non-capturing 그룹에
        (r'([가-힣]{1,4}\s[가-힣]{1,4})(?:이|가)\s+감독', 1),  # 2단어 이름
        (r'([가-힣]{2,5})(?:이|가)\s+감독', 1),                  # 1단어 이름
        # KO: "감독 봉준호" — "감독상/감독부문" 제외
        (r'감독\s+([가-힣]{2,5})(?![상부])', 1),
        # KO: "봉준호 감독" — 이름이 앞에 오는 경우
        (r'([가-힣]{2,5})\s+감독', 1),
        # EN: "directed by Bong Joon-ho"
        (r'[Dd]irected by\s+([A-Z][a-z]+(?:[\s\-][A-Z][a-z]+)+)', 1),
        # EN: "director Bong Joon-ho"
        (r'[Dd]irector[:\s]+([A-Z][a-z]+(?:[\s\-][A-Z][a-z]+)+)', 1),
    ]
    for pat, grp in patterns:
        m = re.search(pat, text)
        if m:
            name = m.group(grp).strip()
            # 한국어 조사로 끝나는 이름 제외 (과, 와, 가, 는 등)
            if _KO_PARTICLES.search(name):
                continue
            if validate_director(name):
                return name
    return None


def _extract_cast(text: str) -> List[str]:
    """텍스트에서 주연배우 추출 (최대 3명)"""
    names = []

    # KO: "송강호, 이선균, 조여정" 형식 (콤마 나열) — 인명 패턴 근처
    # 패턴: 2~4글자 한글 이름이 "이/가 주연" 또는 "출연" 근처 또는 나열
    ko_names = re.findall(r'([가-힣]{2,4})(?:\s*,\s*[가-힣]{2,4})*\s*(?:등이?\s*)?(?:주연|출연|주인공)', text)
    if not ko_names:
        # 더 넓은 패턴: 이름 열거형
        ko_names = re.findall(r'([가-힣]{2,4})\s*(?:역|배역)', text)

    # 연속 나열 파싱 (예: "송강호, 이선균, 조여정, 최우식")
    if not ko_names:
        # 인트로 텍스트에서 한글 이름 3회 이상 연속 콤마 구분
        segments = re.findall(r'([가-힣]{2,4})(?:\s*,\s*[가-힣]{2,4}){1,4}', text)
        for seg in segments:
            parts = re.findall(r'[가-힣]{2,4}', seg)
            if parts:
                ko_names.extend(parts)

    # EN: "starring Song Kang-ho, Lee Sun-kyun"
    en_match = re.search(r'[Ss]tarring\s+((?:[A-Z][a-z]+(?:[\s\-][A-Z][a-z]+)+(?:,\s*)?){1,3})', text)
    if en_match:
        en_names = [n.strip() for n in re.split(r',\s*', en_match.group(1)) if n.strip()]
        names.extend(en_names)

    # 한국어 이름 중복 제거 후 합산
    seen = set()
    for n in ko_names:
        n = n.strip()
        if n and n not in seen and validate_director(n):
            seen.add(n)
            names.append(n)

    return names[:3]


def _extract_date(text: str) -> Optional[str]:
    """텍스트에서 개봉일 YYYY-MM-DD 추출"""
    # KO: "2019년 5월 30일" / "2019년 5월"
    m = re.search(r'(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일', text)
    if m:
        y, mo, d = m.group(1), m.group(2).zfill(2), m.group(3).zfill(2)
        candidate = f"{y}-{mo}-{d}"
        if validate_date(candidate):
            return candidate

    # EN: "May 30, 2019" or "30 May 2019"
    month_map = {'january':'01','february':'02','march':'03','april':'04','may':'05',
                 'june':'06','july':'07','august':'08','september':'09',
                 'october':'10','november':'11','december':'12'}
    m = re.search(
        r'(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})',
        text, re.IGNORECASE
    )
    if not m:
        m = re.search(
            r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})',
            text, re.IGNORECASE
        )
        if m:
            mo = month_map[m.group(1).lower()]
            d = m.group(2).zfill(2)
            y = m.group(3)
            candidate = f"{y}-{mo}-{d}"
            if validate_date(candidate):
                return candidate
    else:
        d = m.group(1).zfill(2)
        mo = month_map[m.group(2).lower()]
        y = m.group(3)
        candidate = f"{y}-{mo}-{d}"
        if validate_date(candidate):
            return candidate

    return None


# ─────────────────────────────────────────
# IMDB 헬퍼
# ─────────────────────────────────────────

def _imdb_search(title: str) -> Optional[dict]:
    """IMDB API 검색 (IMDB_API_KEY 필요)"""
    if not IMDB_API_KEY:
        return None
    try:
        r = requests.get(
            f'https://imdb-api.com/en/API/SearchMovie/{IMDB_API_KEY}/{requests.utils.quote(title)}',
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            results = r.json().get('results', [])
            return results[0] if results else None
    except Exception as e:
        logger.debug("IMDB 검색 오류: %s", e)
    return None


def _imdb_detail(imdb_id: str) -> Optional[dict]:
    """IMDB 상세 정보"""
    if not IMDB_API_KEY or not imdb_id:
        return None
    try:
        r = requests.get(
            f'https://imdb-api.com/en/API/Title/{IMDB_API_KEY}/{imdb_id}',
            timeout=REQUEST_TIMEOUT,
        )
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.debug("IMDB 상세 오류: %s", e)
    return None


# ─────────────────────────────────────────
# Ollama 헬퍼
# ─────────────────────────────────────────

def _ollama_available() -> bool:
    try:
        r = requests.get(f'{OLLAMA_HOST}/api/tags', timeout=2)
        return r.status_code == 200
    except Exception:
        return False


def _ollama_extract(prompt: str) -> Optional[str]:
    if not _ollama_available():
        return None
    try:
        r = requests.post(
            f'{OLLAMA_HOST}/api/generate',
            json={'model': OLLAMA_MODEL, 'prompt': prompt, 'stream': False,
                  'options': {'temperature': 0.1, 'num_predict': 50}},
            timeout=30,
        )
        if r.status_code == 200:
            return r.json().get('response', '').strip()
    except Exception as e:
        logger.debug("Ollama 오류: %s", e)
    return None


# ─────────────────────────────────────────
# 공개 검색 함수
# ─────────────────────────────────────────

@_cached
def search_director(asset_nm: str) -> Optional[str]:
    """
    영화명으로 감독 검색.
    전략: Wikipedia KO (다중 쿼리) → Wikipedia EN → IMDB → Ollama LLM
    """
    norm = _normalize_query(asset_nm)

    # 1차: Wikipedia KO — 여러 쿼리 변형 시도
    ko_queries = list(dict.fromkeys([
        f'{asset_nm} 영화',
        f'{norm} 영화',
        f'{norm} (영화)',
    ]))
    for q in ko_queries:
        _, ko_text = _wiki_search_and_intro(q, 'ko')
        if ko_text:
            name = _extract_director(ko_text)
            if name:
                logger.info("[director] %s → %s (Wiki KO)", asset_nm, name)
                return name

    # 2차: Wikipedia EN — 여러 쿼리 변형 시도
    en_queries = list(dict.fromkeys([
        f'{asset_nm} film',
        f'{norm} film',
    ]))
    for q in en_queries:
        _, en_text = _wiki_search_and_intro(q, 'en')
        if en_text:
            name = _extract_director(en_text)
            if name:
                logger.info("[director] %s → %s (Wiki EN)", asset_nm, name)
                return name

    # 3차: IMDB
    item = _imdb_search(asset_nm)
    if item:
        detail = _imdb_detail(item.get('id', ''))
        if detail:
            directors = detail.get('directorList', [])
            if directors:
                name = directors[0].get('name', '').strip()
                if name and validate_director(name):
                    logger.info("[director] %s → %s (IMDB)", asset_nm, name)
                    return name

    # 4차: Ollama LLM
    response = _ollama_extract(f'영화 "{asset_nm}"의 감독 이름만 한 줄로 답해줘. 모르면 "없음".')
    if response and response not in ('없음', '') and validate_director(response):
        logger.info("[director] %s → %s (Ollama)", asset_nm, response)
        return response

    logger.warning("[director] %s → 검색 실패", asset_nm)
    return None


@_cached
def search_cast_lead(asset_nm: str, genre: str = '') -> List[str]:
    """
    영화명으로 주연배우 검색 (최대 3명).
    전략: IMDB → Wikipedia KO 폴백
    """
    # 1차: IMDB
    item = _imdb_search(asset_nm)
    if item:
        detail = _imdb_detail(item.get('id', ''))
        if detail:
            cast = [a.get('name', '').strip() for a in detail.get('actorList', [])[:3]]
            cast = [c for c in cast if c and validate_director(c)]
            if cast:
                logger.info("[cast_lead] %s → %s (IMDB)", asset_nm, cast)
                return cast

    # 2차: Wikipedia KO
    _, ko_text = _wiki_search_and_intro(f'{asset_nm} 영화', 'ko')
    if ko_text:
        cast = _extract_cast(ko_text)
        if cast:
            logger.info("[cast_lead] %s → %s (Wiki KO)", asset_nm, cast)
            return cast

    # 3차: Wikipedia EN
    _, en_text = _wiki_search_and_intro(f'{asset_nm} film', 'en')
    if en_text:
        cast = _extract_cast(en_text)
        if cast:
            logger.info("[cast_lead] %s → %s (Wiki EN)", asset_nm, cast)
            return cast

    logger.warning("[cast_lead] %s → 검색 실패", asset_nm)
    return []


@_cached
def search_rating(asset_nm: str) -> Optional[str]:
    """
    영화명으로 연령등급 검색.
    전략: KMRB → IMDB 폴백
    """
    # 1차: KMRB (stub)
    rating = _kmrb_search(asset_nm)
    if rating and validate_rating(rating):
        return rating

    # 2차: IMDB
    item = _imdb_search(asset_nm)
    if item:
        detail = _imdb_detail(item.get('id', ''))
        if detail:
            raw = detail.get('contentRating', '').strip()
            mapped = _IMDB_TO_KR.get(raw.upper(), raw)
            if mapped and validate_rating(mapped):
                logger.info("[rating] %s → %s (IMDB)", asset_nm, mapped)
                return mapped

    logger.warning("[rating] %s → 검색 실패", asset_nm)
    return None


@_cached
def search_release_date(asset_nm: str) -> Optional[str]:
    """
    영화명으로 개봉일 검색.
    전략: IMDB → Wikipedia KO → Wikipedia EN
    """
    # 1차: IMDB
    item = _imdb_search(asset_nm)
    if item:
        detail = _imdb_detail(item.get('id', ''))
        if detail:
            raw = detail.get('releaseDate', '').strip()
            if raw and validate_date(raw):
                logger.info("[release_date] %s → %s (IMDB)", asset_nm, raw)
                return raw

    # 2차: Wikipedia KO
    _, ko_text = _wiki_search_and_intro(f'{asset_nm} 영화', 'ko')
    if ko_text:
        date_str = _extract_date(ko_text)
        if date_str:
            logger.info("[release_date] %s → %s (Wiki KO)", asset_nm, date_str)
            return date_str

    # 3차: Wikipedia EN
    _, en_text = _wiki_search_and_intro(f'{asset_nm} film', 'en')
    if en_text:
        date_str = _extract_date(en_text)
        if date_str:
            logger.info("[release_date] %s → %s (Wiki EN)", asset_nm, date_str)
            return date_str

    logger.warning("[release_date] %s → 검색 실패", asset_nm)
    return None


# ─────────────────────────────────────────
# 내부 — KMRB / 등급 매핑
# ─────────────────────────────────────────

def _kmrb_search(asset_nm: str) -> Optional[str]:
    """KMRB 연동 (현재 미구현 stub)"""
    return None


_IMDB_TO_KR = {
    'G':     '전체관람가',
    'PG':    '12세이상관람가',
    'PG-13': '15세이상관람가',
    'R':     '18세이상관람가',
    'NC-17': '청소년관람불가',
}
