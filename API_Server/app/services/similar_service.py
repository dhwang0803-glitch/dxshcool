from app.services.base_service import BaseService


class SimilarService(BaseService):
    async def get_similar_vods(self, asset_id: str, limit: int = 10) -> dict:
        """유사 콘텐츠 조회. asset_id는 full_asset_id 또는 series_nm 모두 허용."""
        # Primary: serving.vod_recommendation (CONTENT_BASED via source_vod_id)
        # asset_id가 full_asset_id일 수도, series_nm일 수도 있으므로 양쪽 매칭
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
                    LEFT JOIN public.vod src
                        ON COALESCE(src.series_nm, src.asset_nm) = se.series_nm
                    WHERE src.full_asset_id = $1 OR se.series_nm = $1
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

        # Fallback: 동일 장르 (full_asset_id 또는 series_nm 모두 허용)
        items = await self.query(
            """
            SELECT v2.full_asset_id AS asset_id, v2.asset_nm AS title,
                   v2.genre, v2.poster_url,
                   NULL::float AS score,
                   ROW_NUMBER() OVER ()::int AS rank
            FROM public.vod v2
            WHERE v2.genre = (
                SELECT v1.genre FROM public.vod v1
                WHERE v1.full_asset_id = $1 OR v1.series_nm = $1
                LIMIT 1
            )
              AND v2.full_asset_id <> $1
              AND COALESCE(v2.series_nm, v2.asset_nm) <> $1
            LIMIT $2
            """,
            asset_id,
            limit,
        )
        return {"items": items, "source": "genre_fallback"}


similar_service = SimilarService()

# 하위 호환
get_similar_vods = similar_service.get_similar_vods
