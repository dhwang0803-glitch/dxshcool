"""시청예약 알림 체커 — 30초마다 도래한 예약을 WebSocket으로 push."""

import logging

from app.services.db import get_pool

log = logging.getLogger(__name__)


async def check_reservations():
    """도래한 시청예약을 처리하고 WebSocket 알림 전송."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            UPDATE public.watch_reservation
            SET notified = TRUE
            WHERE alert_at <= NOW() AND notified = FALSE
            RETURNING user_id_fk, channel, program_name
            """
        )

    if not rows:
        return

    from app.routers.ad import _connections

    for row in rows:
        ws = _connections.get(row["user_id_fk"])
        if ws:
            try:
                await ws.send_json({
                    "type": "reservation_alert",
                    "channel": row["channel"],
                    "program_name": row["program_name"],
                    "message": (
                        f"채널 {row['channel']}번에서 "
                        f"{row['program_name']}이(가) 곧 시작됩니다"
                    ),
                })
            except Exception:
                log.warning(
                    "Failed to push reservation alert to user=%s",
                    row["user_id_fk"],
                )

    log.info("reservation_checker: %d alerts sent", len(rows))
