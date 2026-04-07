from app.services.base_service import BaseService


class SimilarService(BaseService):
    async def get_similar_vods(self, asset_id: str, limit: int = 10) -> dict:
        """유사 콘텐츠 조회 — vod_series_embedding 384D cosine 유사도 기반.

        asset_id는 full_asset_id 또는 series_nm 모두 허용.
        """
        # Primary: vod_series_embedding cosine similarity (메타데이터 384D)
        try:
            items = await self.query(
                """
                WITH base AS (
                    SELECT se.series_nm, se.embedding
                    FROM public.vod_series_embedding se
                    LEFT JOIN public.vod src
                        ON COALESCE(src.series_nm, src.asset_nm) = se.series_nm
                    WHERE src.full_asset_id = $1 OR se.series_nm = $1
                    LIMIT 1
                )
                SELECT se2.representative_vod_id AS asset_id,
                       se2.series_nm AS title,
                       se2.ct_cl AS genre,
                       se2.poster_url,
                       1 - (se2.embedding <=> base.embedding) AS score,
                       ROW_NUMBER() OVER (ORDER BY se2.embedding <=> base.embedding) AS rank
                FROM public.vod_series_embedding se2, base
                WHERE se2.series_nm <> base.series_nm
                  AND COALESCE(se2.poster_url, '') <> ''
                ORDER BY se2.embedding <=> base.embedding
                LIMIT $2
                """,
                asset_id,
                limit,
            )
            if items:
                return {"items": items, "source": "meta_embedding"}
        except Exception:
            pass

        # Fallback: 동일 장르 — 시리즈 단위 중복 제거
        items = await self.query(
            """
            SELECT DISTINCT ON (COALESCE(v2.series_nm, v2.asset_nm))
                   COALESCE(se.representative_vod_id, v2.full_asset_id) AS asset_id,
                   COALESCE(v2.series_nm, v2.asset_nm) AS title,
                   v2.genre,
                   COALESCE(se.poster_url, v2.poster_url) AS poster_url,
                   NULL::float AS score,
                   ROW_NUMBER() OVER ()::int AS rank
            FROM public.vod v2
            LEFT JOIN public.vod_series_embedding se
                ON se.series_nm = COALESCE(v2.series_nm, v2.asset_nm)
            WHERE v2.genre = (
                SELECT v1.genre FROM public.vod v1
                WHERE v1.full_asset_id = $1 OR v1.series_nm = $1
                LIMIT 1
            )
              AND v2.full_asset_id <> $1
              AND COALESCE(v2.series_nm, v2.asset_nm) <> $1
              AND COALESCE(COALESCE(se.poster_url, v2.poster_url), '') <> ''
            ORDER BY COALESCE(v2.series_nm, v2.asset_nm)
            LIMIT $2
            """,
            asset_id,
            limit,
        )
        return {"items": items, "source": "genre_fallback"}


similar_service = SimilarService()

# 하위 호환
get_similar_vods = similar_service.get_similar_vods
