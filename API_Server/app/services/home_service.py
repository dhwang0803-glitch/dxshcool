from app.services.db import get_pool


async def get_banner(user_id: str | None = None) -> list[dict]:
    """히어로 배너 3단 구조.

    1단: hybrid_recommendation (유저별 top 5, 히어로 캐러셀) — 로그인 유저
    2단: popular_recommendation (비개인화 top 5) — 항상
    3단: hybrid_recommendation (top 6~10, 하단 개인화) — 로그인 유저 (1단 중복 제거)
    비로그인 시 2단만 반환.
    """
    pool = await get_pool()
    seen: set[str] = set()
    items: list[dict] = []

    def _append_rows(rows):
        for r in rows:
            nm = r["series_nm"] or r["asset_nm"]
            if nm in seen:
                continue
            seen.add(nm)
            items.append({
                "series_nm": nm,
                "title": r["asset_nm"],
                "poster_url": r["poster_url"],
                "category": r["ct_cl"],
                "score": r["score"],
            })

    async with pool.acquire() as conn:
        # 1단: hybrid_recommendation 히어로 top 5 (로그인 유저만)
        if user_id:
            try:
                rows = await conn.fetch(
                    """
                    SELECT r.vod_id_fk, r.score,
                           v.series_nm, v.asset_nm, v.poster_url, v.ct_cl
                    FROM serving.hybrid_recommendation r
                    JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                    WHERE r.user_id_fk = $1
                      AND (r.expires_at IS NULL OR r.expires_at > NOW())
                    ORDER BY r.rank
                    LIMIT 5
                    """,
                    user_id,
                )
                _append_rows(rows)
            except Exception:
                pass

        # 2단: popular_recommendation (항상)
        try:
            rows = await conn.fetch(
                """
                SELECT pr.vod_id_fk, pr.score,
                       v.series_nm, v.asset_nm, v.poster_url, v.ct_cl
                FROM serving.popular_recommendation pr
                JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
                WHERE pr.expires_at IS NULL OR pr.expires_at > NOW()
                ORDER BY pr.score DESC
                LIMIT 5
                """,
            )
            _append_rows(rows)
        except Exception:
            pass

        # 3단: hybrid_recommendation (로그인 유저만)
        if user_id:
            try:
                rows = await conn.fetch(
                    """
                    SELECT r.vod_id_fk, r.score,
                           v.series_nm, v.asset_nm, v.poster_url, v.ct_cl
                    FROM serving.hybrid_recommendation r
                    JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                    WHERE r.user_id_fk = $1
                      AND (r.expires_at IS NULL OR r.expires_at > NOW())
                    ORDER BY r.rank
                    LIMIT 10
                    """,
                    user_id,
                )
                _append_rows(rows)
            except Exception:
                pass

    return items


async def get_sections() -> list[dict]:
    """CT_CL 4종 × Top 20 인기 추천."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pr.ct_cl, pr.rank, pr.score, pr.vod_id_fk,
                   v.series_nm, v.asset_nm, v.poster_url
            FROM serving.popular_recommendation pr
            JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
            ORDER BY pr.ct_cl, pr.rank
            """
        )

    sections: dict[str, list] = {}
    for r in rows:
        ct = r["ct_cl"]
        if ct not in sections:
            sections[ct] = []
        sections[ct].append(
            {
                "series_nm": r["series_nm"] or r["asset_nm"],
                "title": r["asset_nm"],
                "poster_url": r["poster_url"],
                "score": r["score"],
                "rank": r["rank"],
            }
        )

    return [{"ct_cl": ct, "vod_list": vods} for ct, vods in sections.items()]


async def get_personalized_sections(user_id: str) -> list[dict]:
    """장르별 시청 비중 기반 개인화 섹션. 시청 이력 없으면 None 반환."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 유저의 장르별 시청 횟수 집계
        genre_rows = await conn.fetch(
            """
            SELECT v.genre, COUNT(*) AS cnt
            FROM public.watch_history wh
            JOIN public.vod v ON wh.vod_id_fk = v.full_asset_id
            WHERE wh.user_id_fk = $1 AND v.genre IS NOT NULL
            GROUP BY v.genre
            ORDER BY cnt DESC
            """,
            user_id,
        )

        if not genre_rows:
            return None

        total = sum(r["cnt"] for r in genre_rows)
        watched_genres = {r["genre"] for r in genre_rows}

        # 전체 장르 목록 조회 (미시청 장르 추출용)
        all_genres = await conn.fetch(
            """
            SELECT DISTINCT genre FROM public.vod
            WHERE genre IS NOT NULL
            """
        )
        all_genre_set = {r["genre"] for r in all_genres}
        unwatched = all_genre_set - watched_genres

        # popular_recommendation 전체 로드
        pop_rows = await conn.fetch(
            """
            SELECT pr.ct_cl, pr.rank, pr.score, pr.vod_id_fk,
                   v.series_nm, v.asset_nm, v.poster_url, v.genre
            FROM serving.popular_recommendation pr
            JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
            ORDER BY pr.rank
            """
        )

    # 장르별 VOD 인덱스 구성
    genre_vods: dict[str, list] = {}
    for r in pop_rows:
        g = r["genre"]
        if g and g not in genre_vods:
            genre_vods[g] = []
        if g:
            genre_vods[g].append({
                "series_nm": r["series_nm"] or r["asset_nm"],
                "asset_nm": r["asset_nm"],
                "poster_url": r["poster_url"],
            })

    # 시청 비중 내림차순 섹션 구성
    sections = []
    for r in genre_rows:
        genre = r["genre"]
        ratio = round(r["cnt"] / total * 100)
        vods = genre_vods.get(genre, [])[:20]
        if vods:
            sections.append({
                "genre": genre,
                "view_ratio": ratio,
                "vod_list": vods,
            })

    # 미시청 장르 "새로운 장르 도전" 섹션 추가
    if unwatched:
        challenge_genre = next(
            (g for g in unwatched if g in genre_vods and genre_vods[g]),
            None,
        )
        if challenge_genre:
            sections.append({
                "genre": "새로운 장르 도전",
                "view_ratio": 0,
                "vod_list": genre_vods[challenge_genre][:20],
            })

    return sections
