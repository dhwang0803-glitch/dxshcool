from app.services.base_service import BaseService
from app.services.exceptions import INSUFFICIENT_POINTS


class PurchaseService(BaseService):
    async def create(
        self, user_id: str, series_nm: str, option_type: str, points_used: int
    ) -> dict:
        """포인트 차감 + purchase_history + point_history 트랜잭션."""
        async with await self.acquire() as conn:
            # 0) 이미 유효한 구매 존재 여부
            existing = await conn.fetchrow(
                """
                SELECT option_type, points_used, expires_at
                FROM public.purchase_history
                WHERE user_id_fk = $1 AND series_nm = $2
                  AND (option_type = 'permanent'
                       OR (option_type = 'rental' AND expires_at > NOW()))
                ORDER BY purchased_at DESC
                LIMIT 1
                """,
                user_id,
                series_nm,
            )
            if existing:
                balance = await self.get_point_balance(user_id, conn=conn)
                return {
                    "series_nm": series_nm,
                    "option_type": existing["option_type"],
                    "points_used": 0,
                    "remaining_points": balance,
                    "expires_at": existing["expires_at"],
                }

            async with conn.transaction():
                # 1) 잔액 확인 (같은 conn으로 트랜잭션 격리 유지)
                balance = await self.get_point_balance(user_id, conn=conn)
                if balance < points_used:
                    raise INSUFFICIENT_POINTS(balance, points_used)

                # 2) expires_at
                expires_at = None
                if option_type == "rental":
                    expires_row = await conn.fetchrow(
                        "SELECT NOW() + INTERVAL '48 hours' AS ea"
                    )
                    expires_at = expires_row["ea"]

                # 3) purchase_history INSERT
                purchase_row = await conn.fetchrow(
                    """
                    INSERT INTO public.purchase_history
                        (user_id_fk, series_nm, option_type, points_used, expires_at)
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING purchase_id
                    """,
                    user_id,
                    series_nm,
                    option_type,
                    points_used,
                    expires_at,
                )

                # 4) point_history INSERT (차감)
                await conn.execute(
                    """
                    INSERT INTO public.point_history
                        (user_id_fk, type, amount, description, related_purchase_id)
                    VALUES ($1, 'use', $2, $3, $4)
                    """,
                    user_id,
                    points_used,
                    f"{series_nm} {option_type}",
                    purchase_row["purchase_id"],
                )

                remaining = balance - points_used

        return {
            "series_nm": series_nm,
            "option_type": option_type,
            "points_used": points_used,
            "remaining_points": remaining,
            "expires_at": expires_at,
        }


purchase_service = PurchaseService()

# 하위 호환
create_purchase = purchase_service.create
