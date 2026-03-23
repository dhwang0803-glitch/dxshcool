"""알림 관리 — 목록 조회 / 읽음 처리 / 삭제."""

from fastapi import APIRouter, Depends

from app.models.notification import NotificationItem, NotificationListResponse
from app.routers.auth import get_current_user
from app.services import notification_service
from app.services.exceptions import NOTIFICATION_NOT_FOUND

router = APIRouter()


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    current_user: str = Depends(get_current_user),
):
    """알림 목록 (최신순, 전체)."""
    notifications = await notification_service.get_notifications(current_user)
    unread = sum(1 for n in notifications if not n["read"])
    items = [
        NotificationItem(
            id=n["notification_id"],
            type=n["type"],
            title=n["title"],
            message=n["message"],
            image_url=n["image_url"],
            read=n["read"],
            created_at=n["created_at"],
        )
        for n in notifications
    ]
    return NotificationListResponse(
        items=items, total=len(items), unread_count=unread
    )


@router.patch("/{notification_id}/read")
async def read_notification(
    notification_id: int,
    current_user: str = Depends(get_current_user),
):
    """알림 읽음 처리."""
    ok = await notification_service.mark_read(current_user, notification_id)
    if not ok:
        raise NOTIFICATION_NOT_FOUND()
    return {"success": True}


@router.post("/read-all")
async def read_all_notifications(
    current_user: str = Depends(get_current_user),
):
    """전체 읽음 처리."""
    count = await notification_service.mark_all_read(current_user)
    return {"updated": count}


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: int,
    current_user: str = Depends(get_current_user),
):
    """알림 삭제."""
    ok = await notification_service.delete_notification(
        current_user, notification_id
    )
    if not ok:
        raise NOTIFICATION_NOT_FOUND()
    return {"deleted": True}
