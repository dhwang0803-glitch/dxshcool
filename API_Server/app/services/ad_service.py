"""광고 서비스 — serving.shopping_ad 조회."""

import json
import logging
import os
from urllib.parse import quote

from app.services.db import get_pool

log = logging.getLogger(__name__)

# OCI Object Storage base URL (광고 GIF 서빙용)
_OCI_REGION = os.getenv("OCI_REGION")
_OCI_NAMESPACE = os.getenv("OCI_NAMESPACE")
_OCI_AD_BUCKET = os.getenv("OCI_AD_BUCKET", "vod-ad-gifs")


def _to_oci_url(relative_path: str | None) -> str | None:
    """상대경로(ad_gifs/xxx.gif)를 OCI 전체 URL로 변환."""
    if not relative_path:
        return None
    if relative_path.startswith("http"):
        return relative_path
    if not _OCI_REGION or not _OCI_NAMESPACE:
        log.warning("OCI_REGION/OCI_NAMESPACE 미설정 — ad_image_url 그대로 반환")
        return relative_path
    object_name = quote(relative_path, safe="/")
    return (
        f"https://objectstorage.{_OCI_REGION}.oraclecloud.com"
        f"/n/{_OCI_NAMESPACE}/b/{_OCI_AD_BUCKET}/o/{object_name}"
    )


async def _get_nearest_schedule(pool, product_name: str) -> dict | None:
    """제철장터 상품의 현재 시각 이후 가장 가까운 편성 1건 조회."""
    row = await pool.fetchrow(
        """
        SELECT broadcast_date, start_time, end_time
        FROM public.seasonal_market
        WHERE product_name = $1
          AND (broadcast_date > (NOW() AT TIME ZONE 'Asia/Seoul')::date
               OR (broadcast_date = (NOW() AT TIME ZONE 'Asia/Seoul')::date
                   AND end_time > (NOW() AT TIME ZONE 'Asia/Seoul')::time))
        ORDER BY broadcast_date, start_time
        LIMIT 1
        """,
        product_name,
    )
    if not row:
        return None
    return {
        "broadcast_date": row["broadcast_date"].isoformat(),
        "start_time": row["start_time"].strftime("%H:%M"),
        "end_time": row["end_time"].strftime("%H:%M"),
    }


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
        data = {
            "shopping_ad_id": r["shopping_ad_id"],
            "ad_category": r["ad_category"],
            "signal_source": r["signal_source"],
            "score": float(r["score"]),
            "ad_image_url": _to_oci_url(r["ad_image_url"]),
            "product_name": r["product_name"],
            "channel": r["channel"],
        }
        # ad_hints JSON을 data에 풀어서 프론트엔드에 전달
        if r["ad_hints"]:
            try:
                hints = json.loads(r["ad_hints"])
                if isinstance(hints, dict):
                    data.update(hints)
            except (json.JSONDecodeError, TypeError):
                pass

        # 제철장터: seasonal_market 테이블에서 가장 가까운 미래 편성을 실시간 조회
        if ad_type == "seasonal_market" and r["product_name"]:
            schedule = await _get_nearest_schedule(pool, r["product_name"])
            if schedule:
                data.update(schedule)
            else:
                # 미래 편성 없으면 null 처리 (프론트에서 fallback)
                data["broadcast_date"] = None
                data["start_time"] = None
                data["end_time"] = None

        results.append({
            "type": "ad_popup",
            "ad_type": ad_type,
            "vod_id": r["vod_id_fk"],
            "time_sec": int(r["ts_start"]),
            "data": data,
        })

    if results:
        log.info("ad_service: vod=%s t=%.1f → %d ads", vod_id, time_sec, len(results))

    return results
