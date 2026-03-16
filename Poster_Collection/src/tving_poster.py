"""
Tving 포스터 수집 모듈.

전략:
  1. build_index() — Tving 사이트맵(~10,807 P-code URL)을 병렬 크롤링하여
     title→og:image 인덱스를 JSON으로 캐시 (1회 실행, ~60초).
  2. search() — 캐시된 인덱스에서 (base_series_nm, season_num)으로 매칭.

사용 예:
    from Poster_Collection.src import tving_poster
    # 최초 1회
    tving_poster.build_index()
    # 포스터 검색 (asset_nm에서 시즌 파싱 후)
    r = tving_poster.search("신서유기", season=2)
    # -> {"image_url": "https://image.tving.com/...", "width": 500, "height": 750}
"""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ───────────────── 허용 채널 (방송사) 필터 ──────────────────────────────────
# 이 목록에 없는 채널의 콘텐츠는 포스터 매칭 대상에서 제외됨.
# KBS·MBC·SBS (지상파), JTBC·MBN·TV조선·채널A (종편),
# tvN·OCN·Mnet·Olive·XtvN (CJ ENM 계열), 티빙 오리지널 등
ALLOWED_CHANNELS: frozenset[str] = frozenset({
    # 지상파
    "KBS", "KBS1", "KBS2", "KBS W", "KBS Joy", "KBS Drama",
    "MBC", "MBC every1", "MBC M", "MBC ON", "iMBC",
    "SBS", "SBS Plus", "SBS FiL", "SBS funE",
    "EBS", "EBS1", "EBS2",
    # 종편
    "JTBC", "JTBC2", "JTBC3", "JTBC4",
    "MBN", "TV조선", "TV CHOSUN", "채널A",
    # CJ ENM 계열 (tvN 포함)
    "tvN", "OCN", "Mnet", "Olive", "XtvN", "tvN SHOW", "ONSTYLE",
    "CJ ENM", "CJENM",
    # ENA (드라마 채널 — 이상한 변호사 우영우 등)
    "ENA",
    # 티빙 오리지널
    "TVING", "티빙", "TVING Original",
})

# 채널 캐시: p_code → channel 문자열 (중복 HTTP 요청 방지)
_CHANNEL_CACHE: dict[str, str] = {}

_SITEMAP_URL = "https://notice.tving.com/sitemap/sitemap_0.txt"
_IMG_BASE = "https://image.tving.com"
_DEFAULT_INDEX_PATH = Path(__file__).parents[1] / "config" / "tving_index.json"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# ─────────────────────────────── season 파싱 ──────────────────────────────────

_SEASON_PATS = [
    re.compile(r'[Ss]eason\s*(\d+)'),   # Season 2 / season2
    re.compile(r'시즌\s*(\d+)'),          # 시즌2 / 시즌 2
    re.compile(r'\bS(\d{1,2})\b'),       # S2 / S02
    re.compile(r'\s(\d+)부'),            # 2부작
]
_TRAIL_NUM = re.compile(r'\s+(\d{1,2})$')   # 끝 숫자 "신서유기 2"


def _parse_season_from_title(title: str) -> tuple[str, int]:
    """
    Tving 타이틀에서 (base_name, season) 추출.
    "신서유기 2" → ("신서유기", 2)
    "주먹이 운다 시즌3" → ("주먹이 운다", 3)
    "윤스테이" → ("윤스테이", 1)
    """
    s = title.strip()
    for pat in _SEASON_PATS:
        m = pat.search(s)
        if m:
            season = int(m.group(1))
            base = pat.sub("", s).strip(" -")
            return base, season
    m = _TRAIL_NUM.search(s)
    if m:
        season = int(m.group(1))
        base = s[:m.start()].strip()
        return base, season
    return s, 1


def parse_season_from_asset_nm(asset_nm: str) -> tuple[str, int]:
    """
    asset_nm에서 시즌 번호 추출.
    "신서유기 시즌2 01회" → ("신서유기", 2)
    "아는형님 S2 001회" → ("아는형님", 2)
    "마녀들 2 01회"     → ("마녀들", 2)
    "윤스테이 01회"     → ("윤스테이", 1)
    """
    for pat in _SEASON_PATS:
        m = pat.search(asset_nm)
        if m:
            season = int(m.group(1))
            base = pat.sub("", asset_nm)
            base = re.sub(r'\s*\d+\s*(?:회|화|ep\.?\s*\d+)', '', base, flags=re.I)
            return base.strip(), season
    # 회차 제거 후 남은 부분에서 trailing 숫자 체크
    base = re.sub(r'\s*\d+\s*(?:회|화)', '', asset_nm).strip()
    m = _TRAIL_NUM.search(base)
    if m:
        season = int(m.group(1))
        base = base[:m.start()].strip()
        return base, season
    return base, 1


# ─────────────────────────────── 인덱스 빌드 ─────────────────────────────────

def _fetch_one(p_code: str) -> dict | None:
    """P-code 페이지에서 og:title / og:image 추출."""
    try:
        r = requests.get(
            f"https://www.tving.com/contents/{p_code}",
            headers=_HEADERS,
            timeout=10,
        )
        if r.status_code != 200:
            return None
        html = r.text

        # og:image (CAIP0400 landscape) → CAIP0900 vertical(portrait)으로 변환
        m_img = re.search(r'property="og:image"\s+content="([^"]+)"', html)
        if not m_img:
            m_img = re.search(r'content="([^"]+)"\s+property="og:image"', html)
        og_image = m_img.group(1) if m_img else None
        if not og_image or "image.tving.com" not in og_image:
            return None
        # CAIP0400(landscape) → CAIP0900(vertical portrait)
        og_image = og_image.replace("/CAIP0400/", "/CAIP0900/")

        # og:title → "신서유기 2 17화 | TVING" → "신서유기 2"
        m_title = re.search(r'property="og:title"\s+content="([^"]+)"', html)
        if not m_title:
            m_title = re.search(r'content="([^"]+)"\s+property="og:title"', html)
        if not m_title:
            return None
        raw_title = m_title.group(1)
        # " | TVING" 제거
        clean = re.sub(r'\s*\|.*$', '', raw_title).strip()
        # 끝의 "N화", "제N화", "EP.N" 제거
        clean = re.sub(r'\s+(?:제?\s*\d+\s*화|ep\.?\s*\d+)\s*$', '', clean, flags=re.I).strip()

        base, season = _parse_season_from_title(clean)
        return {
            "p_code": p_code,
            "raw_title": clean,
            "base_nm": base,
            "season": season,
            "image_url": og_image,
        }
    except Exception:
        return None


def build_index(
    index_path: str | Path = _DEFAULT_INDEX_PATH,
    workers: int = 30,
    force: bool = False,
) -> dict:
    """
    Tving 사이트맵의 모든 P-code 페이지를 병렬 크롤링하여 인덱스를 빌드.
    이미 index_path가 있으면 스킵 (force=True로 재빌드).

    Returns:
        index dict  { base_nm_lower: [ {p_code, raw_title, base_nm, season, image_url}, ...] }
    """
    index_path = Path(index_path)
    if index_path.exists() and not force:
        logger.info("tving_index 이미 있음 (%s) — 스킵. force=True로 재빌드.", index_path)
        with open(index_path, encoding="utf-8") as f:
            return json.load(f)

    logger.info("Tving 사이트맵 다운로드 중...")
    r = requests.get(_SITEMAP_URL, timeout=15)
    p_codes = [
        line.split("/contents/")[1]
        for line in r.text.strip().split()
        if "/contents/P" in line
    ]
    logger.info("총 %d P-code URL — 병렬(%d workers) 크롤링 시작", len(p_codes), workers)

    index: dict[str, list] = {}
    ok, skip = 0, 0
    t0 = time.time()

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_fetch_one, code): code for code in p_codes}
        for i, future in enumerate(as_completed(futures), 1):
            result = future.result()
            if result:
                key = result["base_nm"].lower()
                index.setdefault(key, []).append(result)
                ok += 1
            else:
                skip += 1
            if i % 500 == 0:
                elapsed = time.time() - t0
                logger.info("[%d/%d] ok=%d skip=%d elapsed=%.0fs", i, len(p_codes), ok, skip, elapsed)

    elapsed = time.time() - t0
    logger.info("완료: ok=%d skip=%d total=%.0fs", ok, skip, elapsed)

    index_path.parent.mkdir(parents=True, exist_ok=True)
    with open(index_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=None)
    logger.info("인덱스 저장 → %s (%d 항목)", index_path, len(index))
    return index


# ─────────────────────────────── 검색 ──────────────────────────────────────

_INDEX_CACHE: dict | None = None


def _load_index(index_path: str | Path = _DEFAULT_INDEX_PATH) -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is not None:
        return _INDEX_CACHE
    index_path = Path(index_path)
    if not index_path.exists():
        raise FileNotFoundError(
            f"tving_index.json 없음: {index_path}\n"
            "먼저 tving_poster.build_index() 를 실행하세요."
        )
    with open(index_path, encoding="utf-8") as f:
        _INDEX_CACHE = json.load(f)
    return _INDEX_CACHE


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()


def _get_channel(p_code: str) -> str:
    """P-code 콘텐츠 페이지에서 방송 채널 추출 (캐시 적용)."""
    if p_code in _CHANNEL_CACHE:
        return _CHANNEL_CACHE[p_code]
    try:
        r = requests.get(
            f"https://www.tving.com/contents/{p_code}",
            headers=_HEADERS,
            timeout=8,
        )
        m = re.search(r'"channel":"([^"]+)"', r.text)
        channel = m.group(1) if m else ""
    except Exception:
        channel = ""
    _CHANNEL_CACHE[p_code] = channel
    return channel


def search(
    series_nm: str,
    season: int = 1,
    ct_cl: str = None,
    release_year: int = None,
    sleep: float = 0.0,
    index_path: str | Path = _DEFAULT_INDEX_PATH,
) -> dict | None:
    """
    Tving 인덱스에서 (series_nm, season)으로 포스터 URL 조회.

    Args:
        series_nm: DB series_nm (예: "신서유기")
        season: 시즌 번호 (기본 1)
        index_path: tving_index.json 경로

    Returns:
        {"image_url": str, "width": int, "height": int} or None
    """
    try:
        index = _load_index(index_path)
    except FileNotFoundError as e:
        logger.warning("%s", e)
        return None

    nm_lower = series_nm.lower()

    def _to_portrait(url: str) -> str:
        """og:image(CAIP0400, 가로) → CAIP0900(세로 포스터) 변환. .png → .jpg 폴백."""
        u = url.replace("/CAIP0400/", "/CAIP0900/")
        u = re.sub(r'\.(png|webp)(/|$)', r'.jpg\2', u)
        return u

    def _pick(entries) -> dict | None:
        """season 정확 매칭 후 채널 검증. 시즌 불일치 또는 허용 채널 외면 None."""
        season_match = [e for e in entries if e["season"] == season]
        if not season_match:
            return None  # 시즌 불일치 → 틀린 포스터보다 None이 낫다
        for e in season_match:
            channel = _get_channel(e["p_code"])
            if channel in ALLOWED_CHANNELS:
                return {"image_url": _to_portrait(e["image_url"]), "width": 500, "height": 750}
            logger.debug("채널 필터 제외: %s (%s) channel=%s", e["raw_title"], e["p_code"], channel)
        return None

    # 1) 정확 키 조회 (exact match 우선)
    if nm_lower in index:
        return _pick(index[nm_lower])

    # 2) 서브스트링 매칭: nm_lower가 키의 일부이거나 키가 nm_lower의 일부
    #    예) "강식당" ⊂ "신서유기 외전 강식당"
    substr_hits = []
    for key, entries in index.items():
        if nm_lower in key or key in nm_lower:
            # 더 짧은 키(정확한 서브매치)일수록 우선
            overlap = len(nm_lower) / len(key) if nm_lower in key else len(key) / len(nm_lower)
            substr_hits.append((overlap, entries))
    if substr_hits:
        substr_hits.sort(key=lambda x: -x[0])
        return _pick(substr_hits[0][1])

    # 3) 유사도 기반 조회 — 한글 3글자 이하는 0.85, 그 이상은 0.75 적용
    min_sim = 0.85 if len(nm_lower) <= 3 else 0.75
    candidates = []
    for key, entries in index.items():
        sim = _similarity(nm_lower, key)
        if sim >= min_sim:
            candidates.extend([(sim, e) for e in entries])

    if not candidates:
        return None

    exact_season = [(sim, e) for sim, e in candidates if e["season"] == season]
    ranked = sorted(exact_season or candidates, key=lambda x: -x[0])
    best_sim, best = ranked[0]
    if best_sim < min_sim:
        return None

    return {"image_url": _to_portrait(best["image_url"]), "width": 500, "height": 750}
