"""홈쇼핑 편성표 크롤링 메인 스크립트.

Usage:
    python Shopping_Ad/scripts/crawl_products.py                    # 오늘 날짜 전체 채널
    python Shopping_Ad/scripts/crawl_products.py --date 2026-03-17  # 특정 날짜
    python Shopping_Ad/scripts/crawl_products.py --channel SK스토아   # 특정 채널
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
from Shopping_Ad.src.normalizer import normalize
from Shopping_Ad.src.db_writer import get_conn, upsert_products

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

# 채널명 → 크롤러 클래스 매핑
CRAWLER_MAP = {cls.channel_name: cls for cls in ALL_CRAWLERS}


async def crawl_all(
    target_date: str,
    channel_filter: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """전체 또는 특정 채널 크롤링 → 정규화 → DB 적재.

    Returns:
        채널별 적재 건수 dict.
    """
    crawlers = ALL_CRAWLERS
    if channel_filter:
        cls = CRAWLER_MAP.get(channel_filter)
        if cls is None:
            logger.error("알 수 없는 채널: %s (가능: %s)", channel_filter, list(CRAWLER_MAP.keys()))
            return {}
        crawlers = [cls]

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

        for crawler_cls in crawlers:
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

            # 정규화 적용
            for p in products:
                p["normalized_name"] = normalize(p.get("raw_name", ""))

            logger.info("[%s] %d건 크롤링 완료", crawler.channel_name, len(products))

            if dry_run:
                for p in products[:5]:
                    logger.info(
                        "  [DRY-RUN] %s | %s → %s | %s원",
                        p.get("start_time", "??:??"),
                        p.get("raw_name", ""),
                        p.get("normalized_name", ""),
                        p.get("price", "-"),
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
    parser = argparse.ArgumentParser(description="홈쇼핑 편성표 크롤링 파이프라인")
    parser.add_argument("--date", type=str, default=None, help="크롤링 대상 날짜 (YYYY-MM-DD)")
    parser.add_argument("--channel", type=str, default=None, help="특정 채널만 크롤링")
    parser.add_argument("--dry-run", action="store_true", help="DB 적재 없이 출력만")
    args = parser.parse_args()

    target_date = args.date or date.today().isoformat()

    logger.info("=" * 60)
    logger.info("홈쇼핑 크롤링 시작: date=%s, channel=%s, dry_run=%s",
                target_date, args.channel or "전체", args.dry_run)
    logger.info("=" * 60)

    stats = asyncio.run(crawl_all(target_date, args.channel, args.dry_run))

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
