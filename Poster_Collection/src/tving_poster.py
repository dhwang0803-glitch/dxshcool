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
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional

import requests

from Poster_Collection.src.base import PosterBase

logger = logging.getLogger(__name__)

# ───────────────── 허용 채널 (방송사) 필터 ──────────────────────────────────
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
    # ENA (드라마 채널)
    "ENA",
    # 티빙 오리지널
    "TVING", "티빙", "TVING Original",
})

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
    re.compile(r'[Ss]eason\s*(\d+)'),
    re.compile(r'시즌\s*(\d+)'),
    re.compile(r'\bS(\d{1,2})\b'),
    re.compile(r'\s(\d+)부'),
]
_TRAIL_NUM = re.compile(r'\s+(\d{1,2})$')


class TvingPoster(PosterBase):
    """Tving 사이트맵 기반 포스터 검색 클래스.

    _index_cache / _channel_cache는 threading.Lock으로 보호하여
    ThreadPoolExecutor 병렬 크롤링 시 race condition을 방지한다.
    """

    _index_cache: dict | None = None
    _index_lock = threading.Lock()

    _channel_cache: dict[str, str] = {}
    _channel_lock = threading.Lock()

    @staticmethod
    def parse_season_from_title(title: str) -> tuple[str, int]:
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

    @staticmethod
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
        base = re.sub(r'\s*\d+\s*(?:회|화)', '', asset_nm).strip()
        m = _TRAIL_NUM.search(base)
        if m:
            season = int(m.group(1))
            base = base[:m.start()].strip()
            return base, season
        return base, 1

    @staticmethod
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

            m_img = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            if not m_img:
                m_img = re.search(r'content="([^"]+)"\s+property="og:image"', html)
            og_image = m_img.group(1) if m_img else None
            if not og_image or "image.tving.com" not in og_image:
                return None
            og_image = og_image.replace("/CAIP0400/", "/CAIP0900/")

            m_title = re.search(r'property="og:title"\s+content="([^"]+)"', html)
            if not m_title:
                m_title = re.search(r'content="([^"]+)"\s+property="og:title"', html)
            if not m_title:
                return None
            raw_title = m_title.group(1)
            clean = re.sub(r'\s*\|.*$', '', raw_title).strip()
            clean = re.sub(r'\s+(?:제?\s*\d+\s*화|ep\.?\s*\d+)\s*$', '', clean, flags=re.I).strip()

            base, season = TvingPoster.parse_season_from_title(clean)
            return {
                "p_code": p_code,
                "raw_title": clean,
                "base_nm": base,
                "season": season,
                "image_url": og_image,
            }
        except Exception:
            return None

    @classmethod
    def build_index(
        cls,
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
            futures = {ex.submit(cls._fetch_one, code): code for code in p_codes}
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

    @classmethod
    def _load_index(cls, index_path: str | Path = _DEFAULT_INDEX_PATH) -> dict:
        # 빠른 경로: 이미 로드됨 (lock 없이 읽기 — dict 참조는 atomic)
        if cls._index_cache is not None:
            return cls._index_cache
        # 느린 경로: 최초 로드 시 lock으로 보호 (중복 로드 방지)
        with cls._index_lock:
            if cls._index_cache is not None:
                return cls._index_cache
            index_path = Path(index_path)
            if not index_path.exists():
                raise FileNotFoundError(
                    f"tving_index.json 없음: {index_path}\n"
                    "먼저 tving_poster.build_index() 를 실행하세요."
                )
            with open(index_path, encoding="utf-8") as f:
                cls._index_cache = json.load(f)
            return cls._index_cache

    @classmethod
    def _get_channel(cls, p_code: str) -> str:
        """P-code 콘텐츠 페이지에서 방송 채널 추출 (thread-safe 캐시)."""
        with cls._channel_lock:
            if p_code in cls._channel_cache:
                return cls._channel_cache[p_code]
        # lock 밖에서 HTTP 요청 (I/O 블로킹을 lock 안에서 하면 병렬성 저하)
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
        with cls._channel_lock:
            cls._channel_cache[p_code] = channel
        return channel

    @classmethod
    def search(
        cls,
        series_nm: str,
        season: int = 1,
        ct_cl: str = None,
        release_year: int = None,
        sleep: float = 0.0,
        index_path: str | Path = _DEFAULT_INDEX_PATH,
    ) -> dict | None:
        """
        Tving 인덱스에서 (series_nm, season)으로 포스터 URL 조회.

        Returns:
            {"image_url": str, "width": int, "height": int} or None
        """
        try:
            index = cls._load_index(index_path)
        except FileNotFoundError as e:
            logger.warning("%s", e)
            return None

        nm_lower = series_nm.lower()

        def _to_portrait(url: str) -> str:
            u = url.replace("/CAIP0400/", "/CAIP0900/")
            u = re.sub(r'\.(png|webp)(/|$)', r'.jpg\2', u)
            return u

        def _pick(entries) -> dict | None:
            season_match = [e for e in entries if e["season"] == season]
            if not season_match:
                return None
            for e in season_match:
                channel = cls._get_channel(e["p_code"])
                if channel in ALLOWED_CHANNELS:
                    return {"image_url": _to_portrait(e["image_url"]), "width": 500, "height": 750}
                logger.debug("채널 필터 제외: %s (%s) channel=%s", e["raw_title"], e["p_code"], channel)
            return None

        # 1) 정확 키 조회
        if nm_lower in index:
            return _pick(index[nm_lower])

        # 2) 서브스트링 매칭
        substr_hits = []
        for key, entries in index.items():
            if nm_lower in key or key in nm_lower:
                overlap = len(nm_lower) / len(key) if nm_lower in key else len(key) / len(nm_lower)
                substr_hits.append((overlap, entries))
        if substr_hits:
            substr_hits.sort(key=lambda x: -x[0])
            return _pick(substr_hits[0][1])

        # 3) 유사도 기반 조회
        min_sim = 0.85 if len(nm_lower) <= 3 else 0.75
        candidates = []
        for key, entries in index.items():
            sim = cls.title_similarity(nm_lower, key)
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


# ── 싱글턴 + 하위호환 별칭 ──
_tving = TvingPoster()

search = TvingPoster.search
build_index = TvingPoster.build_index
parse_season_from_asset_nm = TvingPoster.parse_season_from_asset_nm
_parse_season_from_title = TvingPoster.parse_season_from_title
_load_index = TvingPoster._load_index
_similarity = TvingPoster.title_similarity
_fetch_one = TvingPoster._fetch_one
_get_channel = TvingPoster._get_channel

# 모듈-레벨 캐시 접근은 TvingPoster 클래스 메서드를 통해서만 (lock 보호)
# 직접 _INDEX_CACHE/_CHANNEL_CACHE 접근은 thread-unsafe이므로 제거
