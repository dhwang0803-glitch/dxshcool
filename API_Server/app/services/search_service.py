"""GNB 통합 검색 — serving.vod_search_index MV 기반.

일반 텍스트 → pg_trgm 검색 (search_text)
초성 입력   → series_nm_chosung LIKE prefix 검색
회차 패턴   → 시리즈 검색 후 에피소드 필터링
"""

import re

from app.services.base_service import BaseService

_CHOSUNG_START = 0x3131
_CHOSUNG_END = 0x314E
_EPISODE_RE = re.compile(r"\s+(\d+)\s*[화회]?\s*$")


def _is_chosung_query(query: str) -> bool:
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
    m = _EPISODE_RE.search(query)
    if m:
        series_part = query[: m.start()].strip()
        episode_num = int(m.group(1))
        if series_part:
            return series_part, episode_num
    return query, None


class SearchService(BaseService):
    async def search(self, query: str, limit: int = 8) -> list[dict]:
        series_query, episode_num = _parse_episode(query)

        async with await self.acquire() as conn:
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


search_service = SearchService()

# 하위 호환
search_vod = search_service.search
