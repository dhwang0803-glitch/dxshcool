"""시청예약 알림 체커 — 30초마다 도래한 예약을 WebSocket push + notifications 기록."""

import logging

from app.services.db import get_pool
from app.services.notification_service import create_reservation_notification

log = logging.getLogger(__name__)


async def _get_schedule_text(pool, program_name: str) -> tuple[str | None, str | None]:
    """seasonal_market에서 가장 가까운 미래 편성의 날짜·시각 문자열 반환."""
    row = await pool.fetchrow(
        """
        SELECT broadcast_date, start_time
        FROM public.seasonal_market
        WHERE product_name = $1
          AND (broadcast_date > (NOW() AT TIME ZONE 'Asia/Seoul')::date
               OR (broadcast_date = (NOW() AT TIME ZONE 'Asia/Seoul')::date
                   AND start_time > (NOW() AT TIME ZONE 'Asia/Seoul')::time))
        ORDER BY broadcast_date, start_time
        LIMIT 1
        """,
        program_name,
    )
    if not row:
        return None, None
    bd = row["broadcast_date"]
    st = row["start_time"]
    date_str = f"{bd.year}년 {bd.month}월 {bd.day}일"
    time_str = st.strftime("%H:%M")
    return date_str, time_str


def _build_message(channel: int, program_name: str,
                   date_str: str | None, time_str: str | None) -> str:
    if date_str and time_str:
        return (
            f"채널 {channel}번에서 {program_name}이(가) "
            f"{date_str} {time_str}분에 시작할 예정입니다"
        )
    return f"채널 {channel}번에서 {program_name}이(가) 곧 시작됩니다"


async def check_reservations():
    """도래한 시청예약을 처리하고 WebSocket 알림 전송 + notifications 테이블 기록."""
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
        date_str, time_str = await _get_schedule_text(pool, row["program_name"])

        # notifications 테이블에 기록
        try:
            await create_reservation_notification(
                row["user_id_fk"], row["channel"], row["program_name"],
                broadcast_date=date_str, start_time=time_str,
            )
        except Exception:
            log.warning(
                "Failed to create notification for user=%s",
                row["user_id_fk"],
            )

        # WebSocket push
        ws = _connections.get(row["user_id_fk"])
        if ws:
            try:
                message = _build_message(
                    row["channel"], row["program_name"], date_str, time_str,
                )
                await ws.send_json({
                    "type": "reservation_alert",
                    "channel": row["channel"],
                    "program_name": row["program_name"],
                    "message": message,
                })
            except Exception:
                log.warning(
                    "Failed to push reservation alert to user=%s",
                    row["user_id_fk"],
                )

    log.info("reservation_checker: %d alerts sent", len(rows))
