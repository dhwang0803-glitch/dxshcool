from app.services.db import get_pool


async def get_watching(user_id: str, limit: int = 10) -> list[dict]:
    """시청 중인 콘텐츠 — watch_history + episode_progress UNION (시리즈 최신 1건)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT series_nm, episode_title, poster_url,
                   completion_rate, watched_at
            FROM (
                SELECT series_nm, episode_title, poster_url,
                       completion_rate, watched_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY series_nm
                           ORDER BY watched_at DESC
                       ) AS rn
                FROM (
                    SELECT COALESCE(v.series_nm, v.asset_nm) AS series_nm,
                           v.asset_nm AS episode_title,
                           v.poster_url,
                           ROUND(wh.completion_rate * 100)::int AS completion_rate,
                           wh.strt_dt AS watched_at
                    FROM public.watch_history wh
                    JOIN public.vod v ON wh.vod_id_fk = v.full_asset_id
                    WHERE wh.user_id_fk = $1
                      AND wh.completion_rate > 0
                      AND wh.completion_rate < 1

                    UNION ALL

                    SELECT ep.series_nm,
                           v.asset_nm AS episode_title,
                           v.poster_url,
                           ep.completion_rate,
                           ep.watched_at
                    FROM public.episode_progress ep
                    JOIN public.vod v ON ep.vod_id_fk = v.full_asset_id
                    WHERE ep.user_id_fk = $1
                      AND ep.completion_rate > 0
                      AND ep.completion_rate < 100
                ) combined
            ) ranked
            WHERE rn = 1
            ORDER BY watched_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    return [
        {
            "series_nm": r["series_nm"],
            "episode_title": r["episode_title"],
            "poster_url": r["poster_url"],
            "completion_rate": r["completion_rate"],
            "watched_at": r["watched_at"],
        }
        for r in rows
    ]


async def get_profile(user_id: str) -> dict | None:
    """유저 프로필 — user_name(sha2_hash 앞 5자) + point_balance 실시간 집계."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        user_row = await conn.fetchrow(
            'SELECT sha2_hash FROM public."user" WHERE sha2_hash = $1',
            user_id,
        )
        if not user_row:
            return None

        balance_row = await conn.fetchrow(
            """
            SELECT COALESCE(
                SUM(CASE WHEN type = 'earn' THEN amount ELSE -amount END),
                0
            ) AS balance
            FROM public.point_history
            WHERE user_id_fk = $1
            """,
            user_id,
        )

    return {
        "user_name": user_id[:5],
        "point_balance": int(balance_row["balance"]),
    }


async def get_points(user_id: str, limit: int = 20) -> dict:
    """포인트 잔액 + 최근 내역."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        balance_row = await conn.fetchrow(
            """
            SELECT COALESCE(
                SUM(CASE WHEN type = 'earn' THEN amount ELSE -amount END),
                0
            ) AS balance
            FROM public.point_history
            WHERE user_id_fk = $1
            """,
            user_id,
        )

        rows = await conn.fetch(
            """
            SELECT type, amount, description, created_at
            FROM public.point_history
            WHERE user_id_fk = $1
            ORDER BY created_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )

    return {
        "balance": int(balance_row["balance"]),
        "history": [
            {
                "type": r["type"],
                "amount": r["amount"],
                "description": r["description"],
                "created_at": r["created_at"],
            }
            for r in rows
        ],
    }


async def get_history(user_id: str, limit: int = 50) -> list[dict]:
    """시청 내역 — watch_history 기본 + episode_progress 실시간 합산 (시리즈 최신 1건)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT series_nm, episode_title, poster_url,
                   completion_rate, watched_at
            FROM (
                SELECT series_nm, episode_title, poster_url,
                       completion_rate, watched_at,
                       ROW_NUMBER() OVER (
                           PARTITION BY series_nm
                           ORDER BY watched_at DESC
                       ) AS rn
                FROM (
                    SELECT COALESCE(v.series_nm, v.asset_nm) AS series_nm,
                           v.asset_nm AS episode_title,
                           v.poster_url,
                           ROUND(wh.completion_rate * 100)::int AS completion_rate,
                           wh.strt_dt AS watched_at
                    FROM public.watch_history wh
                    JOIN public.vod v ON wh.vod_id_fk = v.full_asset_id
                    WHERE wh.user_id_fk = $1

                    UNION ALL

                    SELECT ep.series_nm,
                           v.asset_nm AS episode_title,
                           v.poster_url,
                           ep.completion_rate,
                           ep.watched_at
                    FROM public.episode_progress ep
                    JOIN public.vod v ON ep.vod_id_fk = v.full_asset_id
                    WHERE ep.user_id_fk = $1
                ) combined
            ) ranked
            WHERE rn = 1
            ORDER BY watched_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    return [
        {
            "series_nm": r["series_nm"],
            "episode_title": r["episode_title"],
            "poster_url": r["poster_url"],
            "completion_rate": r["completion_rate"],
            "watched_at": r["watched_at"],
        }
        for r in rows
    ]


async def get_purchases(user_id: str, limit: int = 50) -> list[dict]:
    """구매 내역."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT series_nm, option_type, points_used, purchased_at, expires_at
            FROM public.purchase_history
            WHERE user_id_fk = $1
            ORDER BY purchased_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
    return [
        {
            "series_nm": r["series_nm"],
            "option_type": r["option_type"],
            "points_used": r["points_used"],
            "purchased_at": r["purchased_at"],
            "expires_at": r["expires_at"],
        }
        for r in rows
    ]


async def get_wishlist(user_id: str) -> list[dict]:
    """찜 목록 — 포스터 포함."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT w.series_nm, w.created_at,
                   (SELECT v.poster_url FROM public.vod v
                    WHERE v.series_nm = w.series_nm LIMIT 1) AS poster_url
            FROM public.wishlist w
            WHERE w.user_id_fk = $1
            ORDER BY w.created_at DESC
            """,
            user_id,
        )
    return [
        {
            "series_nm": r["series_nm"],
            "poster_url": r["poster_url"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]
