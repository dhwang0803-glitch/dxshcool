"""CJ온스타일 편성표 크롤러 (JSON API 방식).

API 엔드포인트:
  - broadcast/tvList → 현재/근접 방송 목록 (TV, PLUS 채널)
제한사항: 전체 일간 편성표 API가 아닌, 현재 방송 근처 3건만 반환.
"""

from __future__ import annotations

import json
import logging
import re

from playwright.async_api import Page

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_API_TV_LIST = "https://display-frontapi.cjonstyle.com/broadcast/tvList?bdDt={date_compact}&pmType=P"


class CJOnstyleCrawler(BaseCrawler):
    channel_name = "CJ온스타일"
    url = "https://display-frontapi.cjonstyle.com/broadcast/tvList"

    async def crawl(self, page: Page, target_date: str) -> list[dict]:
        date_compact = target_date.replace("-", "")
        url = _API_TV_LIST.format(date_compact=date_compact)

        try:
            resp = await page.goto(url, wait_until="domcontentloaded")
            if resp and resp.status != 200:
                logger.warning("[CJ온스타일] HTTP %s", resp.status)
                return []

            body = await page.evaluate("() => document.body.innerText")
            data = json.loads(body)
        except Exception:
            logger.exception("[CJ온스타일] API 호출 실패")
            return []

        broadcasts = data.get("result", {}).get("broadcastList", [])
        results: list[dict] = []

        for b in broadcasts:
            pgm_name = b.get("pgmNm")
            if not pgm_name:
                continue

            start_dtm = b.get("bdStrDtm")  # "2026-03-17T17:30:00"
            end_dtm = b.get("bdEndDtm")
            start_time = self._extract_time(start_dtm)
            end_time = self._extract_time(end_dtm)

            # 대표 상품
            rep_item = b.get("repItem")
            if rep_item:
                info = rep_item.get("itemBaseInfo", {})
                price_info = rep_item.get("itemPriceInfo", {})
                raw_name = info.get("displayItemName") or info.get("itemNm") or ""
                if raw_name:
                    results.append({
                        "channel": self.channel_name,
                        "broadcast_date": target_date,
                        "start_time": start_time,
                        "end_time": end_time,
                        "raw_name": raw_name.strip(),
                        "price": self._safe_int(price_info.get("sellPrice")),
                        "product_url": info.get("itemLink"),
                        "image_url": info.get("itemLargeImgUrl") or info.get("itemImgUrl"),
                        "program_name": pgm_name,
                    })

            # 방송 내 추가 아이템
            for item in b.get("itemList", []):
                info = item.get("itemBaseInfo", {})
                price_info = item.get("itemPriceInfo", {})
                raw_name = info.get("displayItemName") or info.get("itemNm") or ""
                if raw_name:
                    results.append({
                        "channel": self.channel_name,
                        "broadcast_date": target_date,
                        "start_time": start_time,
                        "end_time": end_time,
                        "raw_name": raw_name.strip(),
                        "price": self._safe_int(price_info.get("sellPrice")),
                        "product_url": info.get("itemLink"),
                        "image_url": info.get("itemLargeImgUrl") or info.get("itemImgUrl"),
                        "program_name": pgm_name,
                    })

        return results

    @staticmethod
    def _extract_time(dtm: str | None) -> str | None:
        """'2026-03-17T17:30:00' → '17:30'"""
        if not dtm:
            return None
        m = re.search(r"T(\d{2}:\d{2})", dtm)
        return m.group(1) if m else None

    @staticmethod
    def _safe_int(val) -> int | None:
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            digits = re.sub(r"[^\d]", "", str(val))
            return int(digits) if digits else None
