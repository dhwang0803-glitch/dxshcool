"""롯데홈쇼핑 편성표 크롤러 (JSON API 방식).

API 엔드포인트:
  - scheduleLive.lotte → 라이브TV 편성표
  - scheduleOne.lotte  → 원TV 편성표
"""

from __future__ import annotations

import json
import logging
import re

from playwright.async_api import Page

from .base import BaseCrawler

logger = logging.getLogger(__name__)

# 날짜별 편성표 JSON API
_API_LIVE = "https://www.lotteimall.com/main/scheduleLive.lotte?bdDate={date_compact}&date={date_hyphen}"
_API_ONE = "https://www.lotteimall.com/main/scheduleOne.lotte?bdDate={date_compact}&date={date_hyphen}"


class LotteCrawler(BaseCrawler):
    channel_name = "롯데홈쇼핑"
    url = "https://www.lotteimall.com/main/tvschedule.lotte"

    async def crawl(self, page: Page, target_date: str) -> list[dict]:
        date_compact = target_date.replace("-", "")
        results: list[dict] = []

        for label, api_tpl in [("Live", _API_LIVE), ("One", _API_ONE)]:
            url = api_tpl.format(date_compact=date_compact, date_hyphen=target_date)
            try:
                resp = await page.goto(url, wait_until="domcontentloaded")
                if resp and resp.status != 200:
                    logger.warning("[롯데 %s] HTTP %s", label, resp.status)
                    continue

                body = await page.evaluate("() => document.body.innerText")
                data = json.loads(body)
                prods = data.get("body", {}).get("prod", [])
                logger.info("[롯데 %s] %d건 수신", label, len(prods))

                for p in prods:
                    raw_name = p.get("name", "").strip()
                    if not raw_name:
                        continue

                    results.append({
                        "channel": f"롯데홈쇼핑_{label}",
                        "broadcast_date": target_date,
                        "start_time": p.get("stime"),
                        "end_time": p.get("etime"),
                        "raw_name": raw_name,
                        "price": self._parse_price(p.get("price_disc") or p.get("price_orig")),
                        "product_url": self._build_url(p.get("linkInfo")),
                        "image_url": p.get("img_url"),
                        "program_name": p.get("brand"),
                    })
            except Exception:
                logger.exception("[롯데 %s] 파싱 실패", label)

        return results

    @staticmethod
    def _parse_price(val) -> int | None:
        if not val:
            return None
        digits = re.sub(r"[^\d]", "", str(val))
        return int(digits) if digits else None

    @staticmethod
    def _build_url(path: str | None) -> str | None:
        if not path:
            return None
        if path.startswith("http"):
            return path
        return f"https://www.lotteimall.com{path}"
