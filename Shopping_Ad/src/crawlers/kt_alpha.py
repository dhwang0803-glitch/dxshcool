"""KT알파쇼핑 편성표 크롤러 (JSON API 방식).

API 엔드포인트:
  /display/web/emc/display/broadcast?broadcastType=tv&dateValue=YYYYMMDD
  → tvScheduleList[] (편성 26건) + productList[] (상품 상세)
"""

from __future__ import annotations

import json
import logging
import re

from playwright.async_api import Page

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_API_URL = (
    "https://www.kshop.co.kr/display/web/emc/display/broadcast"
    "?broadcastType=tv&dateValue={date_compact}"
)
_IMG_BASE = "https://image.kshop.co.kr"


class KTAlphaCrawler(BaseCrawler):
    channel_name = "KT알파쇼핑"
    url = "https://www.kshop.co.kr/"

    async def crawl(self, page: Page, target_date: str) -> list[dict]:
        date_compact = target_date.replace("-", "")
        api_url = _API_URL.format(date_compact=date_compact)

        try:
            resp = await page.goto(api_url, wait_until="domcontentloaded")
            if resp and resp.status != 200:
                logger.warning("[KT알파쇼핑] HTTP %s", resp.status)
                return []

            body = await page.evaluate("() => document.body.innerText")
            data = json.loads(body)
        except Exception:
            logger.exception("[KT알파쇼핑] API 호출 실패")
            return []

        schedule_list = data.get("data", {}).get("tvScheduleList", [])
        results: list[dict] = []

        for sched in schedule_list:
            start_time = self._extract_time(sched.get("brdBgnDtm"))
            end_time = self._extract_time(sched.get("brdClDtm"))
            program_name = sched.get("schdNm")

            for prod in sched.get("productList", []):
                raw_name = prod.get("prdNm") or prod.get("mobPrdNm") or ""
                raw_name = raw_name.strip()
                if not raw_name:
                    continue

                price = self._extract_price(prod.get("priceSummary"))
                img_path = prod.get("prdImgFlNm")
                image_url = f"{_IMG_BASE}{img_path}" if img_path else None

                dp_prd_id = prod.get("dpPrdId")
                product_url = (
                    f"https://www.kshop.co.kr/display/web/prd/detail/{dp_prd_id}"
                    if dp_prd_id else None
                )

                results.append({
                    "channel": self.channel_name,
                    "broadcast_date": target_date,
                    "start_time": start_time,
                    "end_time": end_time,
                    "raw_name": raw_name,
                    "price": price,
                    "product_url": product_url,
                    "image_url": image_url,
                    "program_name": program_name,
                })

        return results

    @staticmethod
    def _extract_time(dtm: str | None) -> str | None:
        """'2026-03-16T14:40:25.000+0000' → '23:40' (KST = UTC+9)"""
        if not dtm:
            return None
        m = re.search(r"T(\d{2}):(\d{2})", dtm)
        if not m:
            return None
        hour = int(m.group(1)) + 9  # UTC → KST
        minute = m.group(2)
        if hour >= 24:
            hour -= 24
        return f"{hour:02d}:{minute}"

    @staticmethod
    def _extract_price(price_summary) -> int | None:
        """priceSummary dict/str에서 가격 추출."""
        if not price_summary:
            return None
        text = str(price_summary)
        # slPrc 또는 nmlSlPrc 찾기
        for key in ["slPrc", "nmlSlPrc", "dpSlPrc"]:
            m = re.search(rf"'{key}':\s*(\d+\.?\d*)", text)
            if m:
                val = float(m.group(1))
                if val > 0:
                    return int(val)
        return None
