from app.services.db import get_pool


async def get_similar_vods(asset_id: str, limit: int = 10) -> dict:
    pool = await get_pool()

    # Primary: serving.vod_recommendation (CONTENT_BASED via source_vod_id)
    # source_vod_id는 시리즈 대표 VOD ID이므로, 입력 에피소드 → 대표 ID 매핑 후 조회
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT r.vod_id_fk AS asset_id, r.rank, r.score,
                       v.asset_nm AS title, v.genre, v.poster_url
                FROM serving.vod_recommendation r
                JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                WHERE r.source_vod_id = (
                    SELECT se.representative_vod_id
                    FROM vod_series_embedding se
                    JOIN vod src ON COALESCE(src.series_nm, src.asset_nm) = se.series_nm
                    WHERE src.full_asset_id = $1
                    LIMIT 1
                )
                  AND r.recommendation_type IN ('VISUAL_SIMILARITY', 'CONTENT_BASED')
                  AND (r.expires_at IS NULL OR r.expires_at > NOW())
                ORDER BY r.rank
                LIMIT $2
                """,
                asset_id, limit,
            )
        if rows:
            return {"items": [dict(r) for r in rows], "source": "vector_similarity"}
    except Exception:
        pass  # serving 스키마 미생성 시 fallback으로 전환

    # Fallback: 동일 장르
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT v.full_asset_id AS asset_id, v.asset_nm AS title,
                   v.genre, v.poster_url,
                   NULL::float AS score,
                   ROW_NUMBER() OVER ()::int AS rank
            FROM public.vod v
            WHERE v.genre = (SELECT genre FROM public.vod WHERE full_asset_id = $1)
              AND v.full_asset_id <> $1
            LIMIT $2
            """,
            asset_id, limit,
        )
    return {"items": [dict(r) for r in rows], "source": "genre_fallback"}
