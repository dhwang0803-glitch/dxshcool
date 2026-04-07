from app.services.base_service import BaseService


class UserService(BaseService):
    # ── 시청 기록 공통 쿼리 ─────────────────────────────────────────

    async def _watch_union(
        self, user_id: str, limit: int, wh_where: str = ""
    ) -> list[dict]:
        """watch_history + episode_progress UNION (시리즈 최신 1건).

        wh_where: watch_history 추가 WHERE 조건 (e.g. 시청 중만).
        """
        return await self.query(
            f"""
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
                      {wh_where}

                    UNION ALL

                    SELECT ep.series_nm,
                           v.asset_nm AS episode_title,
                           v.poster_url,
                           ep.completion_rate,
                           ep.watched_at
                    FROM public.episode_progress ep
                    JOIN public.vod v ON ep.vod_id_fk = v.full_asset_id
                    WHERE ep.user_id_fk = $1
                      {"AND ep.completion_rate > 0 AND ep.completion_rate < 100" if wh_where else ""}
                ) combined
            ) ranked
            WHERE rn = 1
            ORDER BY watched_at DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )

    # ── 공개 메서드 ─────────────────────────────────────────────────

    async def get_watching(self, user_id: str, limit: int = 10) -> list[dict]:
        """시청 중인 콘텐츠 (0 < completion_rate < 100)."""
        return await self._watch_union(
            user_id,
            limit,
            wh_where="AND wh.completion_rate > 0 AND wh.completion_rate < 1",
        )

    async def get_history(self, user_id: str, limit: int = 50) -> list[dict]:
        """전체 시청 내역."""
        return await self._watch_union(user_id, limit)

    async def get_profile(self, user_id: str) -> dict | None:
        """유저 프로필 — user_name + point_balance."""
        user_row = await self.query_one(
            'SELECT sha2_hash FROM public."user" WHERE sha2_hash = $1',
            user_id,
        )
        if not user_row:
            return None
        balance = await self.get_point_balance(user_id)
        return {"user_name": user_id[:5], "point_balance": balance}

    async def get_points(self, user_id: str, limit: int = 20) -> dict:
        """포인트 잔액 + 최근 내역."""
        balance = await self.get_point_balance(user_id)
        history = await self.query(
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
        return {"balance": balance, "history": history}

    async def get_purchases(self, user_id: str, limit: int = 50) -> list[dict]:
        """구매 내역."""
        return await self.query(
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

    async def get_wishlist(self, user_id: str) -> list[dict]:
        """찜 목록 — 포스터 포함."""
        return await self.query(
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


user_service = UserService()

# 하위 호환
get_watching = user_service.get_watching
get_profile = user_service.get_profile
get_points = user_service.get_points
get_history = user_service.get_history
get_purchases = user_service.get_purchases
get_wishlist = user_service.get_wishlist
