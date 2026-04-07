"""시청 진행률 인메모리 버퍼 — 30초 heartbeat를 60초 batch flush로 DB 쓰기 감소."""

import asyncio
import logging

from app.services.db import get_pool

log = logging.getLogger(__name__)

# (user_id, vod_id) → {"completion_rate": int, "series_nm": str}
_buffer: dict[tuple[str, str], dict] = {}
_lock = asyncio.Lock()


async def buffer_progress(
    user_id: str, vod_id: str, series_nm: str, completion_rate: int
):
    """heartbeat 수신 → 메모리에 최신 값만 보관 (DB 안 침)."""
    async with _lock:
        _buffer[(user_id, vod_id)] = {
            "completion_rate": completion_rate,
            "series_nm": series_nm,
        }


async def flush_progress():
    """버퍼를 DB에 일괄 UPSERT 후 비움. 60초마다 호출."""
    async with _lock:
        items = list(_buffer.items())
        _buffer.clear()

    if not items:
        return

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            """
            INSERT INTO public.episode_progress
                (user_id_fk, vod_id_fk, series_nm, completion_rate, watched_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id_fk, vod_id_fk)
            DO UPDATE SET completion_rate = $4, watched_at = NOW()
            """,
            [
                (uid, vid, d["series_nm"], d["completion_rate"])
                for (uid, vid), d in items
            ],
        )
    log.info("flush_progress: %d items written to DB", len(items))


def buffer_size() -> int:
    """현재 버퍼에 쌓인 항목 수 (모니터링용)."""
    return len(_buffer)
