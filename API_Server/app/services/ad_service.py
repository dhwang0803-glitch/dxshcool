"""광고 서비스 — serving.shopping_ad 조회."""

import logging

from app.services.db import get_pool

log = logging.getLogger(__name__)


async def get_ads_for_vod(vod_id: str, time_sec: float) -> list[dict]:
    """VOD 재생 중 현재 타임스탬프에 해당하는 광고 후보를 조회한다.

    Args:
        vod_id: VOD full_asset_id
        time_sec: 현재 재생 시간(초)

    Returns:
        매칭된 광고 목록 (priority 순)
    """
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT shopping_ad_id, vod_id_fk, ts_start, ts_end,
               ad_category, signal_source, score,
               ad_hints, ad_action_type,
               ad_image_url, product_name, channel
        FROM serving.shopping_ad
        WHERE vod_id_fk = $1
          AND ts_start <= $2
          AND ts_end >= $2
          AND expires_at > NOW()
        ORDER BY score DESC
        """,
        vod_id,
        time_sec,
    )

    results = []
    for r in rows:
        ad_type = (
            "local_gov" if r["ad_action_type"] == "local_gov_popup"
            else "seasonal_market"
        )
        results.append({
            "type": "ad_popup",
            "ad_type": ad_type,
            "vod_id": r["vod_id_fk"],
            "time_sec": int(r["ts_start"]),
            "data": {
                "shopping_ad_id": r["shopping_ad_id"],
                "ad_category": r["ad_category"],
                "signal_source": r["signal_source"],
                "score": float(r["score"]),
                "ad_hints": r["ad_hints"],
                "ad_image_url": r["ad_image_url"],
                "product_name": r["product_name"],
                "channel": r["channel"],
            },
        })

    if results:
        log.info("ad_service: vod=%s t=%.1f → %d ads", vod_id, time_sec, len(results))

    return results
