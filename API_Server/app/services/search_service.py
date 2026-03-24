"""GNB 통합 검색 — serving.vod_search_index MV 기반.

일반 텍스트 → pg_trgm 검색 (search_text)
초성 입력   → series_nm_chosung LIKE prefix 검색
회차 패턴   → 시리즈 검색 후 에피소드 필터링
"""

import re

from app.services.db import get_pool

# 한글 초성 유니코드 범위: ㄱ(0x3131) ~ ㅎ(0x314E)
_CHOSUNG_START = 0x3131
_CHOSUNG_END = 0x314E

# 회차 패턴: "3화", "3회", 또는 쿼리 끝 숫자
_EPISODE_RE = re.compile(r"\s+(\d+)\s*[화회]?\s*$")


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


def _parse_episode(query: str) -> tuple[str, int | None]:
    """쿼리에서 회차 패턴 분리. ('응답하라', 3) 또는 ('응답하라', None)."""
    m = _EPISODE_RE.search(query)
    if m:
        series_part = query[: m.start()].strip()
        episode_num = int(m.group(1))
        if series_part:
            return series_part, episode_num
    return query, None


async def search_vod(query: str, limit: int = 8) -> list[dict]:
    """VOD 통합 검색. 초성이면 chosung 컬럼, 아니면 trgm 검색. 회차 감지 시 에피소드 반환."""
    series_query, episode_num = _parse_episode(query)

    pool = await get_pool()
    async with pool.acquire() as conn:
        # 1) 시리즈 레벨 검색
        if _is_chosung_query(series_query):
            rows = await conn.fetch(
                """
                SELECT series_nm, asset_nm, genre, ct_cl, poster_url
                FROM serving.vod_search_index
                WHERE series_nm_chosung LIKE $1 || '%'
                ORDER BY series_nm
                LIMIT $2
                """,
                series_query,
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
                series_query,
                limit,
            )

        # 2) 회차 지정 시 → 매칭된 시리즈의 에피소드 검색
        if episode_num is not None and rows:
            series_names = list({r["series_nm"] for r in rows})
            ep_pattern = f"%{episode_num}화%"
            ep_rows = await conn.fetch(
                """
                SELECT DISTINCT ON (v.asset_nm)
                    COALESCE(v.series_nm, v.asset_nm) AS series_nm,
                    v.asset_nm, v.genre, v.ct_cl, v.poster_url
                FROM public.vod v
                WHERE v.series_nm = ANY($1)
                  AND v.asset_nm LIKE $2
                ORDER BY v.asset_nm,
                         CASE SPLIT_PART(v.full_asset_id, '|', 1)
                             WHEN 'kth' THEN 1 WHEN 'cjc' THEN 2
                             WHEN 'hcn' THEN 3 ELSE 4
                         END
                LIMIT $3
                """,
                series_names,
                ep_pattern,
                limit,
            )
            if ep_rows:
                return [dict(r) for r in ep_rows]

    return [dict(r) for r in rows]
