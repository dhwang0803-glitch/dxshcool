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

        # Fallback: 동일 ct_cl 내 임베딩 cosine 유사도 (embedding 미보유 시리즈 대응)
        items = await self.query(
            """
            WITH src_ct AS (
                SELECT v.ct_cl
                FROM public.vod v
                WHERE v.full_asset_id = $1 OR v.series_nm = $1
                LIMIT 1
            )
            SELECT se.representative_vod_id AS asset_id,
                   se.series_nm AS title,
                   se.ct_cl AS genre,
                   se.poster_url,
                   NULL::float AS score,
                   ROW_NUMBER() OVER ()::int AS rank
            FROM public.vod_series_embedding se, src_ct
            WHERE se.ct_cl = src_ct.ct_cl
              AND se.series_nm <> $1
              AND COALESCE(se.poster_url, '') <> ''
              AND se.embedding IS NOT NULL
            ORDER BY RANDOM()
            LIMIT $2
            """,
            asset_id,
            limit,
        )
        return {"items": items, "source": "ct_cl_fallback"}


similar_service = SimilarService()

# 하위 호환
get_similar_vods = similar_service.get_similar_vods
