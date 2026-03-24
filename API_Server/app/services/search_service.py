"""GNB 통합 검색 — serving.vod_search_index MV 기반.

일반 텍스트 → pg_trgm 검색 (search_text)
초성 입력   → series_nm_chosung LIKE prefix 검색
"""

from app.services.db import get_pool

# 한글 초성 유니코드 범위: ㄱ(0x3131) ~ ㅎ(0x314E)
_CHOSUNG_START = 0x3131
_CHOSUNG_END = 0x314E


def _is_chosung_query(query: str) -> bool:
    """입력이 초성 검색인지 판별. 공백/숫자 제외한 한글이 모두 초성이면 True."""
    for ch in query:
        if ch in (" ", "\t"):
            continue
        if ch.isdigit() or ch.isascii():
            continue
        code = ord(ch)
        if not (_CHOSUNG_START <= code <= _CHOSUNG_END):
            return False
    return True


async def search_vod(query: str, limit: int = 8) -> list[dict]:
    """VOD 통합 검색. 초성이면 chosung 컬럼, 아니면 trgm 검색."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if _is_chosung_query(query):
            rows = await conn.fetch(
                """
                SELECT series_nm, asset_nm, genre, ct_cl, poster_url
                FROM serving.vod_search_index
                WHERE series_nm_chosung LIKE $1 || '%'
                ORDER BY series_nm
                LIMIT $2
                """,
                query,
                limit,
            )
        else:
            rows = await conn.fetch(
                """
                SELECT series_nm, asset_nm, genre, ct_cl, poster_url
                FROM serving.vod_search_index
                WHERE search_text ILIKE '%' || $1 || '%'
                ORDER BY similarity(search_text, $1) DESC
                LIMIT $2
                """,
                query,
                limit,
            )
    return [dict(r) for r in rows]
