from app.services.base_service import BaseService


class SimilarService(BaseService):
    async def get_similar_vods(self, asset_id: str, limit: int = 10) -> dict:
        # Primary: serving.vod_recommendation (CONTENT_BASED via source_vod_id)
        try:
            items = await self.query(
                """
                SELECT r.vod_id_fk AS asset_id, r.rank, r.score,
                       v.asset_nm AS title, v.genre, v.poster_url
                FROM serving.vod_recommendation r
                JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                WHERE r.source_vod_id = (
                    SELECT se.representative_vod_id
                    FROM public.vod_series_embedding se
                    JOIN public.vod src ON COALESCE(src.series_nm, src.asset_nm) = se.series_nm
                    WHERE src.full_asset_id = $1
                    LIMIT 1
                )
                  AND r.recommendation_type IN ('VISUAL_SIMILARITY', 'CONTENT_BASED')
                  AND (r.expires_at IS NULL OR r.expires_at > NOW())
                ORDER BY r.rank
                LIMIT $2
                """,
                asset_id,
                limit,
            )
            if items:
                return {"items": items, "source": "vector_similarity"}
        except Exception:
            pass

        # Fallback: 동일 장르
        items = await self.query(
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
            asset_id,
            limit,
        )
        return {"items": items, "source": "genre_fallback"}


similar_service = SimilarService()

# 하위 호환
get_similar_vods = similar_service.get_similar_vods
