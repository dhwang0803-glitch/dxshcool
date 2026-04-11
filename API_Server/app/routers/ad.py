"""WebSocket /ad/popup — 실시간 광고 팝업.

serving.shopping_ad 테이블에서 VOD 재생 타임스탬프 기반으로
광고 후보를 조회하여 클라이언트에 푸시한다.

Client → Server 메시지:
  - playback_update: VOD 재생 시간 전송 → DB 조회 → 광고 푸시
  - ad_action: 광고 액션 (reserve_watch / dismiss / minimize / reopen)
"""

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.ad import AdActionMessage, PlaybackUpdateMessage
from app.services.ad_service import get_ads_for_vod
from app.services.db import get_pool
from app.services.notification_service import create_reservation_notification

router = APIRouter()
log = logging.getLogger(__name__)

# 연결된 클라이언트 관리 (user_id → WebSocket)
_connections: dict[str, WebSocket] = {}

# 유저별 활성 광고 상태 (user_id → list[ad_data])
# 재연결 시 미제거 광고를 다시 전송한다.
_active_ads: dict[str, list[dict]] = {}

# 유저별 이미 전송한 광고 ID (중복 전송 방지)
_sent_ad_ids: dict[str, set[int]] = {}


@router.websocket("/popup")
async def ad_popup(ws: WebSocket):
    """광고 팝업 WebSocket 엔드포인트.

    연결 시 query param으로 user_id 전달:
        ws://host/ad/popup?user_id=sha2_hash

    Server → Client (ad_popup):
        {"type": "ad_popup", "ad_type": "local_gov|seasonal_market",
         "vod_id": "...", "time_sec": 120, "data": {...}}

    Client → Server (ad_action):
        {"type": "ad_action", "action": "reserve_watch|dismiss|minimize|reopen",
         "vod_id": "..."}
    """
    user_id = ws.query_params.get("user_id")
    if not user_id:
        await ws.close(code=4001, reason="user_id query param required")
        return

    await ws.accept()
    _connections[user_id] = ws
    log.info("ad_popup connected: user_id=%s", user_id)

    # 재연결 시 미제거 광고 복원 전송
    pending = _active_ads.get(user_id, [])
    for ad_data in pending:
        await ws.send_json(ad_data)
    if pending:
        log.info("ad_popup restored %d ads for user_id=%s", len(pending), user_id)

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"error": "invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "playback_update":
                await _handle_playback(user_id, PlaybackUpdateMessage(**msg))
            elif msg_type == "ad_action":
                await _handle_action(user_id, AdActionMessage(**msg))
            else:
                await ws.send_json({"error": f"unknown message type: {msg_type}"})

    except WebSocketDisconnect:
        log.info("ad_popup disconnected: user_id=%s", user_id)
    finally:
        _connections.pop(user_id, None)
        _sent_ad_ids.pop(user_id, None)


def _find_active_ad(user_id: str, vod_id: str, ad_type: str) -> dict | None:
    """활성 광고 목록에서 특정 VOD + 광고 타입 찾기."""
    for ad in _active_ads.get(user_id, []):
        if ad.get("vod_id") == vod_id and ad.get("ad_type") == ad_type:
            return ad
    return None


async def _handle_playback(user_id: str, msg: PlaybackUpdateMessage):
    """VOD 재생 시간 수신 → DB 조회 → 미전송 광고 푸시."""
    ads = await get_ads_for_vod(msg.vod_id, msg.time_sec)

    sent = _sent_ad_ids.setdefault(user_id, set())
    ws = _connections.get(user_id)
    if not ws:
        return

    for ad in ads:
        ad_id = ad["data"]["shopping_ad_id"]
        if ad_id in sent:
            continue

        sent.add(ad_id)
        _active_ads.setdefault(user_id, []).append(ad)
        await ws.send_json(ad)
        log.info(
            "ad_pushed: user=%s vod=%s ad_id=%d type=%s",
            user_id, msg.vod_id, ad_id, ad["ad_type"],
        )


async def _handle_action(user_id: str, action: AdActionMessage):
    """클라이언트 광고 액션 처리."""
    log.info(
        "ad_action: user=%s action=%s vod=%s",
        user_id, action.action, action.vod_id,
    )

    if action.action == "reserve_watch":
        ws = _connections.get(user_id)
        ad_info = _find_active_ad(user_id, action.vod_id, "seasonal_market")

        success = False
        if ad_info:
            product_name = ad_info["data"].get("product_name", "제철장터")
            # watch_reservation.channel은 INT (채널 번호). 제철장터 = 25번
            channel_no = 25
            alert_at = datetime.now(timezone.utc)

            try:
                pool = await get_pool()
                await pool.execute(
                    """
                    INSERT INTO public.watch_reservation
                        (user_id_fk, channel, program_name, alert_at)
                    VALUES ($1, $2, $3, $4)
                    """,
                    user_id, channel_no, product_name, alert_at,
                )
                # 알림을 즉시 생성 (reservation_checker 30초 대기 없이)
                await pool.execute(
                    """
                    UPDATE public.watch_reservation
                    SET notified = TRUE
                    WHERE user_id_fk = $1 AND program_name = $2
                      AND alert_at = $3 AND notified = FALSE
                    """,
                    user_id, product_name, alert_at,
                )
                from app.services.reservation_checker import _get_schedule_text
                date_str, time_str = await _get_schedule_text(pool, product_name)
                await create_reservation_notification(
                    user_id, channel_no, product_name,
                    broadcast_date=date_str, start_time=time_str,
                )
                success = True
                log.info("reserve_watch: user=%s product=%s ch=%d", user_id, product_name, channel_no)
            except Exception as e:
                log.error("reserve_watch DB error: %s", e)

        if ws:
            if success:
                await ws.send_json({
                    "type": "ad_response",
                    "action": "reserve_watch",
                    "vod_id": action.vod_id,
                    "message": "시청예약되었습니다",
                })
            else:
                await ws.send_json({
                    "type": "ad_response",
                    "action": "reserve_watch",
                    "vod_id": action.vod_id,
                    "error": "시청예약에 실패했습니다",
                })

    elif action.action == "dismiss":
        # 팝업 완전 제거 — 활성 광고 목록에서 제거 (재연결 시 복원 방지)
        ads = _active_ads.get(user_id, [])
        _active_ads[user_id] = [a for a in ads if a.get("vod_id") != action.vod_id]

    elif action.action in ("minimize", "reopen"):
        # 팝업 최소화/다시 열기 — 클라이언트 측 UI 처리
        pass


async def send_ad_to_user(user_id: str, ad_data: dict):
    """외부 모듈(Shopping_Ad)에서 호출하여 특정 유저에게 광고 전송.

    ad_data 예시:
        {"type": "ad_popup", "ad_type": "local_gov", "vod_id": "...",
         "time_sec": 120, "data": {"image_url": "...", ...}}
    """
    # 활성 광고 목록에 추가 (재연결 시 복원용)
    _active_ads.setdefault(user_id, []).append(ad_data)

    ws = _connections.get(user_id)
    if ws:
        await ws.send_json(ad_data)
