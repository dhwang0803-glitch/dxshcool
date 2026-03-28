from app.services.db import get_pool


async def get_episodes(series_nm: str) -> list[dict]:
    """시리즈의 에피소드 목록 — DISTINCT ON(asset_nm) + provider 우선순위로 중복 제거."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT DISTINCT ON (v.asset_nm)
                   v.full_asset_id, v.asset_nm, v.ct_cl, v.poster_url, v.asset_prod
            FROM public.vod v
            WHERE v.series_nm = $1
            ORDER BY v.asset_nm,
                     CASE SPLIT_PART(v.full_asset_id, '|', 1)
                         WHEN 'kth' THEN 1
                         WHEN 'cjc' THEN 2
                         WHEN 'hcn' THEN 3
                         ELSE 4
                     END
            """,
            series_nm,
        )
    return [
        {
            "asset_id": r["full_asset_id"],
            "episode_title": r["asset_nm"],
            "category": r["ct_cl"],
            "poster_url": r["poster_url"],
            "is_free": r["asset_prod"] == "FOD",
        }
        for r in rows
    ]


async def get_series_progress(user_id: str, series_nm: str) -> dict:
    """특정 시리즈의 에피소드별 시청 진행 현황."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT ep.completion_rate, ep.watched_at,
                   v.asset_nm
            FROM public.episode_progress ep
            JOIN public.vod v ON ep.vod_id_fk = v.full_asset_id
            WHERE ep.user_id_fk = $1 AND ep.series_nm = $2
            ORDER BY ep.watched_at DESC
            """,
            user_id,
            series_nm,
        )

    episodes = [
        {
            "episode_title": r["asset_nm"],
            "completion_rate": r["completion_rate"],
            "watched_at": r["watched_at"],
        }
        for r in rows
    ]

    last = episodes[0] if episodes else None
    return {
        "series_nm": series_nm,
        "last_episode": last["episode_title"] if last else None,
        "last_completion_rate": last["completion_rate"] if last else None,
        "episodes": episodes,
    }


async def update_episode_progress(
    user_id: str, series_nm: str, asset_nm: str, completion_rate: int
) -> dict | None:
    """에피소드 시청 진행률 UPSERT."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # asset_nm → vod_id_fk 조회
        vod_row = await conn.fetchrow(
            """
            SELECT full_asset_id FROM public.vod
            WHERE series_nm = $1 AND asset_nm = $2
            LIMIT 1
            """,
            series_nm,
            asset_nm,
        )
        if not vod_row:
            return None

        row = await conn.fetchrow(
            """
            INSERT INTO public.episode_progress
                (user_id_fk, vod_id_fk, series_nm, completion_rate, watched_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (user_id_fk, vod_id_fk)
            DO UPDATE SET completion_rate = $4, watched_at = NOW()
            RETURNING completion_rate, watched_at
            """,
            user_id,
            vod_row["full_asset_id"],
            series_nm,
            completion_rate,
        )

    return {
        "episode_title": asset_nm,
        "completion_rate": row["completion_rate"],
        "watched_at": row["watched_at"],
    }


async def check_purchase(user_id: str, series_nm: str) -> dict:
    """특정 시리즈 구매 여부 + 만료 확인."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT option_type, expires_at,
                   CASE
                     WHEN option_type = 'permanent' THEN FALSE
                     WHEN expires_at IS NULL THEN FALSE
                     WHEN expires_at > NOW() THEN FALSE
                     ELSE TRUE
                   END AS is_expired
            FROM public.purchase_history
            WHERE user_id_fk = $1 AND series_nm = $2
            ORDER BY purchased_at DESC
            LIMIT 1
            """,
            user_id,
            series_nm,
        )

    if not row:
        return {
            "series_nm": series_nm,
            "purchased": False,
            "option_type": None,
            "expires_at": None,
            "is_expired": None,
        }

    return {
        "series_nm": series_nm,
        "purchased": True,
        "option_type": row["option_type"],
        "expires_at": row["expires_at"],
        "is_expired": row["is_expired"],
    }


async def resolve_vod_id(series_nm: str, asset_nm: str) -> str | None:
    """series_nm + asset_nm → full_asset_id 조회. heartbeat 버퍼용."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT full_asset_id FROM public.vod
            WHERE series_nm = $1 AND asset_nm = $2
            LIMIT 1
            """,
            series_nm,
            asset_nm,
        )
    return row["full_asset_id"] if row else None


async def get_purchase_options(series_nm: str) -> dict:
    """구매 옵션 조회 — FOD 시리즈는 무료."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT asset_prod FROM public.vod
            WHERE series_nm = $1
            LIMIT 1
            """,
            series_nm,
        )

    if not row:
        return {"series_nm": series_nm, "is_free": False, "options": []}

    is_free = row["asset_prod"] == "FOD"

    if is_free:
        return {"series_nm": series_nm, "is_free": True, "options": []}

    return {
        "series_nm": series_nm,
        "is_free": False,
        "options": [
            {"option_type": "rental", "points": 490, "duration": "48h"},
            {"option_type": "permanent", "points": 1490, "duration": None},
        ],
    }
