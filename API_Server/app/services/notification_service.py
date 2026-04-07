"""알림 서비스 — notifications 테이블 CRUD."""

from app.services.base_service import BaseService


class NotificationService(BaseService):
    async def get_list(self, user_id: str) -> list[dict]:
        """유저 알림 목록 (최신순)."""
        return await self.query(
            """
            SELECT notification_id, type, title, message, image_url, read, created_at
            FROM public.notifications
            WHERE user_id_fk = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )

    async def get_unread_count(self, user_id: str) -> int:
        """미읽음 알림 개수."""
        row = await self.query_one(
            """
            SELECT COUNT(*) AS cnt
            FROM public.notifications
            WHERE user_id_fk = $1 AND read = FALSE
            """,
            user_id,
        )
        return row["cnt"] if row else 0

    async def mark_read(self, user_id: str, notification_id: int) -> bool:
        """알림 읽음 처리."""
        result = await self.execute(
            """
            UPDATE public.notifications
            SET read = TRUE
            WHERE notification_id = $1 AND user_id_fk = $2
            """,
            notification_id,
            user_id,
        )
        return result == "UPDATE 1"

    async def mark_all_read(self, user_id: str) -> int:
        """전체 읽음 처리. 갱신 건수 반환."""
        result = await self.execute(
            """
            UPDATE public.notifications
            SET read = TRUE
            WHERE user_id_fk = $1 AND read = FALSE
            """,
            user_id,
        )
        return int(result.split()[-1])

    async def delete(self, user_id: str, notification_id: int) -> bool:
        """알림 삭제."""
        result = await self.execute(
            """
            DELETE FROM public.notifications
            WHERE notification_id = $1 AND user_id_fk = $2
            """,
            notification_id,
            user_id,
        )
        return result == "DELETE 1"

    async def create_reservation_notification(
        self, user_id: str, channel: int, program_name: str
    ):
        """시청예약 도래 시 알림 생성."""
        await self.execute(
            """
            INSERT INTO public.notifications (user_id_fk, type, title, message)
            VALUES ($1, 'reservation', $2, $3)
            """,
            user_id,
            program_name,
            f"채널 {channel}번에서 {program_name}이(가) 곧 시작됩니다",
        )


notification_service = NotificationService()

# 하위 호환
get_notifications = notification_service.get_list
get_unread_count = notification_service.get_unread_count
mark_read = notification_service.mark_read
mark_all_read = notification_service.mark_all_read
delete_notification = notification_service.delete
create_reservation_notification = notification_service.create_reservation_notification
