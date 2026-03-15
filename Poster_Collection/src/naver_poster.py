"""
Naver 이미지 검색 API로 시리즈별 포스터 URL 수집.
직접 실행 X — scripts/에서 import해서 사용.
"""
import os
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()

NAVER_CLIENT_ID = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = os.getenv("NAVER_CLIENT_SECRET")
NAVER_IMAGE_API = "https://openapi.naver.com/v1/search/image"

logger = logging.getLogger(__name__)


def search(series_nm: str, display: int = 5, sleep: float = 0.1) -> dict | None:
    """
    series_nm으로 Naver 이미지 검색 → 가장 적합한 포스터 정보 반환.

    Returns:
        {"image_url": str, "width": int, "height": int} or None
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        raise EnvironmentError("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수 없음")

    query = f"{series_nm} 포스터"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "display": display, "filter": "large"}

    for attempt in range(3):
        try:
            resp = requests.get(
                NAVER_IMAGE_API, headers=headers, params=params, timeout=10
            )
            resp.raise_for_status()
            time.sleep(sleep)
            break
        except requests.RequestException as e:
            logger.warning("Naver API 재시도 %d/3: %s", attempt + 1, e)
            if attempt == 2:
                return None
            time.sleep(2 ** attempt)

    items = resp.json().get("items", [])
    if not items:
        return None

    return _pick_best(series_nm, items)


def _pick_best(series_nm: str, items: list) -> dict | None:
    """
    portrait 이미지 우선, series_nm 포함 여부 보조 기준.
    """
    scored = []
    for item in items:
        w = int(item.get("sizewidth") or 0)
        h = int(item.get("sizeheight") or 0)
        url = item.get("link", "")
        title = item.get("title", "").lower()

        if not url:
            continue

        score = 0
        if h > 0 and w > 0 and h > w:   # 세로형(포스터)
            score += 2
        nm_lower = series_nm.lower()
        if nm_lower in title or nm_lower in url.lower():
            score += 1

        scored.append((score, w, h, url))

    if not scored:
        return None

    scored.sort(key=lambda x: (-x[0], -(x[2] or 0)))  # score 내림차순, height 내림차순
    _, w, h, url = scored[0]
    return {"image_url": url, "width": w, "height": h}
