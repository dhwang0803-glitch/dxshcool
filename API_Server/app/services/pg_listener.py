"""PostgreSQL LISTEN/NOTIFY — 유저 활동 실시간 알림.

purchase_history INSERT, wishlist INSERT/DELETE 시
PG 트리거가 NOTIFY 'user_activity' 발행 → 여기서 수신 → WebSocket push.
Frontend는 'data_updated' 메시지를 받으면 해당 섹션 API를 refetch한다.
"""

import json
import logging

from app.services.db import get_pool

log = logging.getLogger(__name__)


async def start_pg_listener():
    """lifespan에서 시작. PG NOTIFY 채널 구독."""
    pool = await get_pool()
    conn = await pool.acquire()

    def _on_user_activity(conn_ref, pid, channel, payload):
        import asyncio
        asyncio.ensure_future(_handle_user_activity(payload))

    await conn.add_listener("user_activity", _on_user_activity)
    log.info("PG LISTEN 'user_activity' started")

    # conn을 반환하지 않고 유지 (리스너 활성 상태 유지)
    return conn


async def _handle_user_activity(payload: str):
    """NOTIFY payload 수신 → 해당 유저 WebSocket으로 push."""
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        log.warning("Invalid NOTIFY payload: %s", payload)
        return

    user_id = data.get("user_id")
    if not user_id:
        return

    # WebSocket 연결 가져오기 (ad.py의 _connections 활용)
    from app.routers.ad import _connections

    ws = _connections.get(user_id)
    if ws:
        try:
            await ws.send_json({
                "type": "data_updated",
                "table": data.get("table"),
                "action": data.get("action"),
            })
            log.info(
                "data_updated pushed: user=%s table=%s",
                user_id, data.get("table"),
            )
        except Exception:
            log.warning("Failed to push data_updated to user=%s", user_id)
