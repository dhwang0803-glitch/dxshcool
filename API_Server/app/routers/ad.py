"""WebSocket /ad/popup — 실시간 광고 팝업.

Shopping_Ad 브랜치 연동 대기 중.
현재는 연결·메시지 수신·액션 처리 스켈레톤만 구현.
광고 트리거(VOD 재생 중 사물인식 이벤트)는 Shopping_Ad 완료 후 연동 예정.
"""

import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.models.ad import AdActionMessage

router = APIRouter()
log = logging.getLogger(__name__)

# 연결된 클라이언트 관리 (user_id → WebSocket)
_connections: dict[str, WebSocket] = {}


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

    try:
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
                action = AdActionMessage(**msg)
            except (json.JSONDecodeError, Exception) as e:
                await ws.send_json({"error": "invalid message format"})
                continue

            await _handle_action(user_id, action)

    except WebSocketDisconnect:
        log.info("ad_popup disconnected: user_id=%s", user_id)
    finally:
        _connections.pop(user_id, None)


async def _handle_action(user_id: str, action: AdActionMessage):
    """클라이언트 광고 액션 처리."""
    log.info(
        "ad_action: user=%s action=%s vod=%s",
        user_id, action.action, action.vod_id,
    )

    if action.action == "reserve_watch":
        # TODO: Shopping_Ad 연동 — 시청예약 처리
        ws = _connections.get(user_id)
        if ws:
            await ws.send_json({
                "type": "ad_response",
                "action": "reserve_watch",
                "vod_id": action.vod_id,
                "message": "시청예약되었습니다",
            })

    elif action.action == "dismiss":
        # 팝업 완전 제거 — 클라이언트 측 처리, 서버는 로그만
        pass

    elif action.action in ("minimize", "reopen"):
        # 팝업 최소화/다시 열기 — 클라이언트 측 UI 처리
        pass


async def send_ad_to_user(user_id: str, ad_data: dict):
    """외부 모듈(Shopping_Ad)에서 호출하여 특정 유저에게 광고 전송.

    ad_data 예시:
        {"type": "ad_popup", "ad_type": "local_gov", "vod_id": "...",
         "time_sec": 120, "data": {"image_url": "...", ...}}
    """
    ws = _connections.get(user_id)
    if ws:
        await ws.send_json(ad_data)
