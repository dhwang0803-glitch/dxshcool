"""공영쇼핑 편성표 크롤러 (AJAX 캡처 방식).

페이지: https://www.gongyoungshop.kr/tvshopping/tvSchedule.do
데이터: selectScheduleSub.do AJAX 응답 → prdList[]
"""

from __future__ import annotations

import json
import logging
import re

from playwright.async_api import Page

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_IMG_BASE = "https://www.gongyoungshop.kr/comimage/goods"


class GongyoungCrawler(BaseCrawler):
    channel_name = "공영쇼핑"
    url = "https://www.gongyoungshop.kr/tvshopping/tvSchedule.do"

    async def crawl(self, page: Page, target_date: str) -> list[dict]:
        captured_body: list[str] = []

        async def on_response(response):
            if "selectScheduleSub" in response.url and response.status == 200:
                try:
                    body = await response.text()
                    captured_body.append(body)
                except Exception:
                    pass

        page.on("response", on_response)

        await page.goto(self.url, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        if not captured_body:
            logger.warning("[공영쇼핑] selectScheduleSub.do 응답 캡처 실패")
            return []

        try:
            data = json.loads(captured_body[0])
        except (json.JSONDecodeError, IndexError):
            logger.warning("[공영쇼핑] JSON 파싱 실패")
            return []

        prd_list = data.get("prdList", [])
        results = []

        for p in prd_list:
            raw_name = p.get("prdNm", "").strip()
            if not raw_name:
                continue

            # brcBgnDtm: "202603170100" → "01:00"
            start_time = self._parse_dtm(p.get("brcBgnDtm") or p.get("searchBrcBgnDtm"))
            end_time = self._parse_dtm(p.get("brcEndDtm") or p.get("searchBrcEndDtm"))

            price = self._safe_int(p.get("prdPrc") or p.get("cnmerUprc"))

            img_path = p.get("imgUrl") or p.get("fileName")
            image_url = f"{_IMG_BASE}{img_path}" if img_path else None

            goods_no = p.get("goodsNo") or p.get("prdId")
            product_url = (
                f"https://www.gongyoungshop.kr/products/detail.do?goodsNo={goods_no}"
                if goods_no else None
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
                "program_name": p.get("brcPgmNm"),
            })

        return results

    @staticmethod
    def _parse_dtm(dtm: str | None) -> str | None:
        """'202603170100' → '01:00'"""
        if not dtm or len(dtm) < 12:
            return None
        return f"{dtm[8:10]}:{dtm[10:12]}"

    @staticmethod
    def _safe_int(val) -> int | None:
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            digits = re.sub(r"[^\d]", "", str(val))
            return int(digits) if digits else None
