"""BaseService — 모든 서비스 클래스의 공통 기반.

중복 제거 대상:
  - DB 풀 획득 + 쿼리 보일러플레이트 (30+개 함수)
  - 포인트 잔액 계산 (purchase_service, user_service × 2)
  - 테스트 유저 판별 (home_service, recommend_service)
  - 시리즈 중복 제거 (recommend_service × 2, home_service)
"""

from app.services.db import get_pool


class BaseService:
    """비동기 DB 서비스 기반 클래스.

    사용법:
        class VodService(BaseService):
            async def get_detail(self, asset_id):
                row = await self.query_one("SELECT ... WHERE id=$1", asset_id)
                return dict(row) if row else None

        vod_service = VodService()         # 모듈 레벨 싱글턴
        result = await vod_service.get_detail("abc")
    """

    async def _pool(self):
        return await get_pool()

    async def query(self, sql: str, *args) -> list[dict]:
        """SELECT 다건 → list[dict]."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *args)
        return [dict(r) for r in rows]

    async def query_one(self, sql: str, *args) -> dict | None:
        """SELECT 단건 → dict | None."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql, *args)
        return dict(row) if row else None

    async def acquire(self):
        """커넥션 컨텍스트 매니저. 복합 쿼리에서 conn을 직접 사용할 때."""
        pool = await self._pool()
        return pool.acquire()

    async def execute(self, sql: str, *args) -> str:
        """INSERT/UPDATE/DELETE 실행 → 결과 문자열 (e.g. 'DELETE 1')."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            return await conn.execute(sql, *args)

    # ── 공통 유틸리티 ──────────────────────────────────────────────────

    async def is_test_user(self, user_id: str) -> bool:
        """테스터 계정 여부 (is_test 플래그)."""
        try:
            row = await self.query_one(
                'SELECT is_test FROM public."user" WHERE sha2_hash = $1',
                user_id,
            )
            return bool(row and row["is_test"])
        except Exception:
            return False

    _BALANCE_SQL = """
        SELECT COALESCE(
            SUM(CASE WHEN type = 'earn' THEN amount ELSE -amount END), 0
        ) AS balance
        FROM public.point_history WHERE user_id_fk = $1
    """

    async def get_point_balance(self, user_id: str, *, conn=None) -> int:
        """포인트 잔액 계산 (point_history 집계).

        Args:
            conn: 트랜잭션 내에서 호출 시 해당 커넥션을 전달.
                  None이면 풀에서 새 커넥션 획득 (트랜잭션 밖 전용).
        """
        if conn is not None:
            row = await conn.fetchrow(self._BALANCE_SQL, user_id)
        else:
            row = await self.query_one(self._BALANCE_SQL, user_id)
        return int(row["balance"]) if row else 0

    @staticmethod
    async def find_source_vods(
        conn, user_id: str, rec_series_nms: list[str], limit_watched: int = 30,
    ) -> dict[str, str]:
        """추천 VOD별로 유저 최근 시청 VOD 중 가장 유사한 시리즈명을 반환.

        episode_progress에서 최근 시청 시리즈 → vod_series_embedding과 JOIN →
        추천 VOD 임베딩과 pgvector <=> 코사인 거리로 비교.

        Returns:
            {rec_series_nm: source_series_nm}  (매칭 실패 시 해당 키 없음)
        """
        if not rec_series_nms:
            return {}

        rows = await conn.fetch(
            """
            WITH watched_series AS (
                SELECT series_nm, MAX(watched_at) AS last_watched
                FROM public.episode_progress
                WHERE user_id_fk = $1
                GROUP BY series_nm
                ORDER BY last_watched DESC
                LIMIT $3
            ),
            recent_watched AS (
                SELECT ws.series_nm, se.embedding
                FROM watched_series ws
                JOIN public.vod_series_embedding se ON ws.series_nm = se.series_nm
            ),
            rec_vods AS (
                SELECT se.series_nm, se.embedding
                FROM public.vod_series_embedding se
                WHERE se.series_nm = ANY($2::text[])
            )
            SELECT rv.series_nm  AS rec_series_nm,
                   rw.series_nm  AS source_series_nm
            FROM rec_vods rv
            CROSS JOIN LATERAL (
                SELECT series_nm
                FROM recent_watched
                ORDER BY embedding <=> rv.embedding
                LIMIT 1
            ) rw
            """,
            user_id, rec_series_nms, limit_watched,
        )
        return {r["rec_series_nm"]: r["source_series_nm"] for r in rows}

    @staticmethod
    def deduplicate_series(rows, key_fn=None, limit: int = 10) -> list[dict]:
        """시리즈 기준 중복 제거.

        Args:
            rows: asyncpg Record 리스트 또는 dict 리스트
            key_fn: 중복 판별 키 추출 함수. 기본값은 series_nm or asset_nm.
            limit: 최대 반환 건수
        """
        if key_fn is None:
            key_fn = lambda r: r.get("series_nm") or r.get("asset_nm") or r["series_nm"]
        seen = set()
        result = []
        for r in rows:
            row = dict(r) if not isinstance(r, dict) else r
            sid = key_fn(row)
            if sid in seen:
                continue
            seen.add(sid)
            result.append(row)
            if len(result) >= limit:
                break
        return result
