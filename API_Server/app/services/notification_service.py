"""알림 서비스 — notifications 테이블 CRUD."""

from app.services.db import get_pool


async def get_notifications(user_id: str) -> list[dict]:
    """유저 알림 목록 (최신순)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT notification_id, type, title, message, image_url, read, created_at
            FROM public.notifications
            WHERE user_id_fk = $1
            ORDER BY created_at DESC
            """,
            user_id,
        )
    return [dict(r) for r in rows]


async def get_unread_count(user_id: str) -> int:
    """미읽음 알림 개수."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT COUNT(*) AS cnt
            FROM public.notifications
            WHERE user_id_fk = $1 AND read = FALSE
            """,
            user_id,
        )
    return row["cnt"]


async def mark_read(user_id: str, notification_id: int) -> bool:
    """알림 읽음 처리. 성공 시 True."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE public.notifications
            SET read = TRUE
            WHERE notification_id = $1 AND user_id_fk = $2
            """,
            notification_id,
            user_id,
        )
    return result == "UPDATE 1"


async def mark_all_read(user_id: str) -> int:
    """전체 읽음 처리. 갱신 건수 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE public.notifications
            SET read = TRUE
            WHERE user_id_fk = $1 AND read = FALSE
            """,
            user_id,
        )
    # result: "UPDATE N"
    return int(result.split()[-1])


async def delete_notification(user_id: str, notification_id: int) -> bool:
    """알림 삭제. 성공 시 True."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            DELETE FROM public.notifications
            WHERE notification_id = $1 AND user_id_fk = $2
            """,
            notification_id,
            user_id,
        )
    return result == "DELETE 1"


async def create_reservation_notification(
    user_id: str, channel: int, program_name: str
):
    """시청예약 도래 시 알림 생성."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO public.notifications (user_id_fk, type, title, message)
            VALUES ($1, 'reservation', $2, $3)
            """,
            user_id,
            program_name,
            f"채널 {channel}번에서 {program_name}이(가) 곧 시작됩니다",
        )
