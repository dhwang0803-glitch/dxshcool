"""광고 팝업 WebSocket 메시지 스키마."""

from pydantic import BaseModel


class AdPopupMessage(BaseModel):
    """Server → Client: 광고 팝업."""

    type: str = "ad_popup"
    ad_type: str  # "local_gov" | "seasonal_market"
    vod_id: str
    time_sec: int
    data: dict


class AdActionMessage(BaseModel):
    """Client → Server: 유저 광고 액션."""

    type: str = "ad_action"
    action: str  # "reserve_watch" | "dismiss" | "minimize" | "reopen"
    vod_id: str


class PlaybackUpdateMessage(BaseModel):
    """Client → Server: VOD 재생 시간 업데이트."""

    type: str = "playback_update"
    vod_id: str
    time_sec: float
