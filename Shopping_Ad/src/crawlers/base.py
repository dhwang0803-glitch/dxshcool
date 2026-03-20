"""Playwright 기반 제철장터 크롤러 베이스 클래스."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import date

from playwright.async_api import Browser, Page, async_playwright

logger = logging.getLogger(__name__)


class BaseCrawler(ABC):
    """각 채널 크롤러가 상속하는 공통 베이스."""

    channel_name: str = ""
    url: str = ""

    def __init__(self, timeout_ms: int = 30_000, headless: bool = True):
        self.timeout_ms = timeout_ms
        self.headless = headless

    @abstractmethod
    async def crawl(self, page: Page, target_date: str) -> list[dict]:
        """날짜별 편성표 크롤링.

        Returns:
            list of dict with keys:
                channel, broadcast_date, start_time, end_time, product_name
        """

    async def run(self, target_date: str | None = None) -> list[dict]:
        """브라우저를 열고 crawl()을 호출한 뒤 결과를 반환."""
        if target_date is None:
            target_date = date.today().isoformat()

        async with async_playwright() as pw:
            browser: Browser = await pw.chromium.launch(headless=self.headless)
            page: Page = await browser.new_page()
            page.set_default_timeout(self.timeout_ms)
            try:
                results = await self.crawl(page, target_date)
                logger.info(
                    "[%s] %s건 크롤링 완료 (date=%s)",
                    self.channel_name,
                    len(results),
                    target_date,
                )
                return results
            except Exception:
                logger.exception("[%s] 크롤링 실패 (date=%s)", self.channel_name, target_date)
                return []
            finally:
                await browser.close()

    def run_sync(self, target_date: str | None = None) -> list[dict]:
        """동기 래퍼."""
        return asyncio.run(self.run(target_date))
