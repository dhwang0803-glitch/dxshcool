"""LG헬로비전 편성표 크롤러 (AJAX POST 방식).

페이지: https://ch.lghellovision.net/main/mainScheduleList.do
데이터: mainScheduleListAjax.do POST → scheduleList[]
필터: TITLE이 "제철장터"인 항목만 수집 (SUBTITLE = 상품명)
"""

from __future__ import annotations

import json
import logging

from playwright.async_api import Page

from .base import BaseCrawler

logger = logging.getLogger(__name__)

_AJAX_URL = "https://ch.lghellovision.net/main/mainScheduleListAjax.do"
_SO_CODE = "SC40000000"


class LGHellovisionCrawler(BaseCrawler):
    channel_name = "LG헬로비전"
    url = "https://ch.lghellovision.net/main/mainScheduleList.do"

    async def crawl(self, page: Page, target_date: str) -> list[dict]:
        date_compact = target_date.replace("-", "")

        captured: list[bytes] = []

        async def on_response(response):
            if "mainScheduleListAjax" in response.url:
                try:
                    body = await response.body()
                    captured.append(body)
                except Exception:
                    pass

        page.on("response", on_response)

        # 페이지 로드 → AJAX 자동 호출 캡처
        schedule_url = (
            f"{self.url}?soCode=SC00000000&ssoCode={_SO_CODE}"
        )
        await page.goto(schedule_url, wait_until="networkidle")
        await page.wait_for_timeout(2000)

        # 자동 캡처 실패 시 직접 POST
        if not captured:
            resp = await page.request.post(
                _AJAX_URL,
                data={"soCode": _SO_CODE, "startdate": date_compact},
                headers={
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            captured.append(await resp.body())

        if not captured:
            logger.warning("[LG헬로비전] AJAX 응답 캡처 실패")
            return []

        try:
            data = json.loads(captured[0].decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("[LG헬로비전] JSON 파싱 실패")
            return []

        schedule_list = data.get("scheduleList", [])
        results: list[dict] = []

        for item in schedule_list:
            title = item.get("TITLE", "")
            if "제철장터" not in title:
                continue

            subtitle = (item.get("SUBTITLE") or "").strip()
            if not subtitle or item.get("SUBTITLE_YN") != "Y":
                continue

            sh = item.get("START_HOUR", "")
            sm = item.get("START_MINUTE", "")
            eh = item.get("END_HOUR", "")
            em = item.get("END_MINUTE", "")

            start_time = f"{sh}:{sm}" if sh and sm else None
            end_time = f"{eh}:{em}" if eh and em else None

            results.append({
                "channel": self.channel_name,
                "broadcast_date": target_date,
                "start_time": start_time,
                "end_time": end_time,
                "raw_name": subtitle,
                "price": None,
                "product_url": None,
                "image_url": None,
                "program_name": title,
            })

        return results
