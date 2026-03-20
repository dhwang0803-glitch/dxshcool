"""제철장터 편성표 크롤링 메인 스크립트.

Usage:
    python Shopping_Ad/scripts/crawl_products.py                    # 오늘 날짜
    python Shopping_Ad/scripts/crawl_products.py --date 2026-03-17  # 특정 날짜
    python Shopping_Ad/scripts/crawl_products.py --dry-run           # DB 적재 없이 출력만
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date
from pathlib import Path

# 프로젝트 루트를 sys.path에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT.parent))

from Shopping_Ad.src.crawlers import ALL_CRAWLERS
from Shopping_Ad.src.db_writer import get_conn, upsert_products

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


async def crawl_all(
    target_date: str,
    dry_run: bool = False,
) -> dict[str, int]:
    """제철장터 크롤링 → DB 적재.

    Returns:
        채널별 적재 건수 dict.
    """
    from playwright.async_api import async_playwright

    stats: dict[str, int] = {}

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            ignore_https_errors=True,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        for crawler_cls in ALL_CRAWLERS:
            crawler = crawler_cls()
            page = await context.new_page()
            page.set_default_timeout(crawler.timeout_ms)

            logger.info("[%s] 크롤링 시작 (date=%s)", crawler.channel_name, target_date)
            try:
                products = await crawler.crawl(page, target_date)
            except Exception:
                logger.exception("[%s] 크롤링 실패", crawler.channel_name)
                products = []
            finally:
                await page.close()

            logger.info("[%s] %d건 크롤링 완료", crawler.channel_name, len(products))

            if dry_run:
                for p in products[:5]:
                    logger.info(
                        "  [DRY-RUN] %s | %s",
                        p.get("start_time", "??:??"),
                        p.get("product_name", ""),
                    )
                if len(products) > 5:
                    logger.info("  ... 외 %d건", len(products) - 5)
                stats[crawler.channel_name] = len(products)
            else:
                if products:
                    with get_conn() as conn:
                        count = upsert_products(conn, products)
                        stats[crawler.channel_name] = count
                else:
                    stats[crawler.channel_name] = 0

        await browser.close()

    return stats


def main():
    parser = argparse.ArgumentParser(description="제철장터 편성표 크롤링 파이프라인")
    parser.add_argument("--date", type=str, default=None, help="크롤링 대상 날짜 (YYYY-MM-DD)")
    parser.add_argument("--dry-run", action="store_true", help="DB 적재 없이 출력만")
    args = parser.parse_args()

    target_date = args.date or date.today().isoformat()

    logger.info("=" * 60)
    logger.info("제철장터 크롤링 시작: date=%s, dry_run=%s", target_date, args.dry_run)
    logger.info("=" * 60)

    stats = asyncio.run(crawl_all(target_date, args.dry_run))

    logger.info("=" * 60)
    logger.info("크롤링 결과 요약:")
    total = 0
    for ch, count in stats.items():
        logger.info("  %s: %d건", ch, count)
        total += count
    logger.info("  합계: %d건", total)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
