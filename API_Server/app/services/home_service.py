from app.services.db import get_pool


async def _is_test_user(pool, user_id: str) -> bool:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT is_test FROM public."user" WHERE sha2_hash = $1',
                user_id,
            )
        return bool(row and row["is_test"])
    except Exception:
        return False


async def get_banner(user_id: str | None = None) -> list[dict]:
    """히어로 배너 2단 구조.

    1단: popular_recommendation score 내림차순 top 5 — 항상 (비개인화 히어로)
    2단: hybrid_recommendation top 10 — 로그인 유저 (하단 개인화, seen 중복 제거)
    비로그인 시 1단만 반환.
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
        # 1단: popular_recommendation 히어로 top 5 (항상)
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

        # 2단: hybrid_recommendation 개인화 top 10 (로그인 유저만)
        if user_id:
            is_test = await _is_test_user(pool, user_id)
            hybrid_table = "serving.hybrid_recommendation_test" if is_test else "serving.hybrid_recommendation"
            try:
                rows = await conn.fetch(
                    f"""
                    SELECT r.vod_id_fk, r.score,
                           v.series_nm, v.asset_nm, v.poster_url, v.ct_cl
                    FROM {hybrid_table} r
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


_TAG_LABEL = {
    "genre": "추천 인기 {value}",
    "genre_detail": "{value}",
}


async def get_personalized_sections(user_id: str) -> list[dict]:
    """tag_recommendation 태그별 배너 생성. 데이터 없으면 None 반환."""
    pool = await get_pool()
    is_test = await _is_test_user(pool, user_id)
    tag_table = "serving.tag_recommendation_test" if is_test else "serving.tag_recommendation"
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            f"""
            SELECT tr.tag_category, tr.tag_value, tr.tag_rank,
                   tr.vod_id_fk, tr.vod_rank, tr.vod_score,
                   v.series_nm, v.asset_nm, v.poster_url
            FROM {tag_table} tr
            JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
            WHERE tr.user_id_fk = $1
              AND tr.tag_category IN ('genre', 'genre_detail')
              AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
            ORDER BY tr.tag_rank, tr.vod_rank
            """,
            user_id,
        )

    if not rows:
        return None

    # 태그별 그룹핑 + 전체 섹션 간 VOD 중복 제거
    grouped: dict[int, dict] = {}
    seen_vods: set[str] = set()
    for r in rows:
        rank = r["tag_rank"]
        nm = r["series_nm"] or r["asset_nm"]
        if nm in seen_vods:
            continue
        seen_vods.add(nm)
        if rank not in grouped:
            label = _TAG_LABEL.get(r["tag_category"], "{value}").format(value=r["tag_value"])
            grouped[rank] = {
                "genre": label,
                "view_ratio": 100 - (rank - 1) * 15,
                "vod_list": [],
            }
        grouped[rank]["vod_list"].append({
            "series_nm": nm,
            "asset_nm": r["asset_nm"],
            "poster_url": r["poster_url"],
        })

    return [grouped[k] for k in sorted(grouped.keys())]
