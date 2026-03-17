"""SK스토아 편성표 크롤러 (DOM 파싱 방식).

페이지: https://www.skstoa.com/tv_schedule
구조: div.broadcast 내부에 시간 블록(div.time_note) + 상품(input.ga-prd-data)
"""

from __future__ import annotations

import logging
import re

from playwright.async_api import Page

from .base import BaseCrawler

logger = logging.getLogger(__name__)


class SKStoaCrawler(BaseCrawler):
    channel_name = "SK스토아"
    url = "https://www.skstoa.com/tv_schedule"

    async def crawl(self, page: Page, target_date: str) -> list[dict]:
        await page.goto(self.url, wait_until="networkidle")

        # 자바스크립트로 시간 블록 + 상품 데이터를 한 번에 추출
        raw_items = await page.evaluate("""() => {
            const broadcast = document.querySelector('div.broadcast');
            if (!broadcast) return [];

            const results = [];
            let currentTime = '';

            // broadcast 내부의 자식 요소를 순회
            // time_note가 나오면 시간 갱신, ga-prd가 나오면 상품 추가
            const children = broadcast.children;
            for (const child of children) {
                // 시간 블록
                const timebox = child.querySelector('.timebox') || child.querySelector('.time_note');
                if (timebox) {
                    const text = timebox.innerText.trim();
                    const m = text.match(/(\\d{2}:\\d{2})\\s*~\\s*(\\d{2}:\\d{2})/);
                    if (m) {
                        currentTime = m[0];
                    }
                }

                // 상품 블록 (input.ga-prd-data)
                const inputs = child.querySelectorAll('input.ga-prd-data');
                for (const input of inputs) {
                    const name = input.getAttribute('p-name') || '';
                    if (!name) continue;
                    results.push({
                        time: currentTime,
                        name: name,
                        price: input.getAttribute('p-price') || '',
                        brand: input.getAttribute('p-brand') || '',
                        id: input.getAttribute('p-id') || '',
                        category: input.getAttribute('p-category') || '',
                    });
                }
            }
            return results;
        }""")

        results = []
        for item in raw_items:
            raw_name = item.get("name", "").strip()
            if not raw_name:
                continue

            start_time, end_time = self._parse_time(item.get("time", ""))
            price = self._parse_price(item.get("price", ""))
            goods_id = item.get("id", "")
            product_url = (
                f"https://www.skstoa.com/products/{goods_id}" if goods_id else None
            )

            results.append({
                "channel": self.channel_name,
                "broadcast_date": target_date,
                "start_time": start_time,
                "end_time": end_time,
                "raw_name": raw_name,
                "price": price,
                "product_url": product_url,
                "image_url": None,
                "program_name": item.get("brand") or None,
            })

        return results

    @staticmethod
    def _parse_time(text: str) -> tuple[str | None, str | None]:
        m = re.search(r"(\d{2}:\d{2})\s*~\s*(\d{2}:\d{2})", text)
        if m:
            return m.group(1), m.group(2)
        return None, None

    @staticmethod
    def _parse_price(val: str) -> int | None:
        if not val:
            return None
        try:
            f = float(val)
            return int(f) if f > 0 else None
        except (ValueError, TypeError):
            digits = re.sub(r"[^\d]", "", val)
            return int(digits) if digits else None
