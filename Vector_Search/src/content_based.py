"""메타데이터 벡터 기반 유사 VOD 검색."""

from Vector_Search.src.base import VectorSearchBase


class ContentSearcher(VectorSearchBase):
    """SBERT 384차원 메타데이터 벡터 기반 유사 VOD 검색."""

    def search(self, vod_id: str, conn, top_n: int = None) -> list[dict]:
        """메타데이터 벡터 기반 유사 VOD TOP-N 반환 (시리즈 대표 임베딩 사용).

        vod_series_embedding(시리즈당 1건, ~14.8K)을 검색하여
        에피소드 중복 없이 시리즈 다양성이 보장된 결과를 반환한다.
        반환: [{"vod_id": str, "content_score": float}, ...]
        """
        config = self.load_config()
        if top_n is None:
            top_n = config["ensemble"]["top_n"]
        probes = config["search"]["series_ivfflat_probes"]

        cur = conn.cursor()

        cur.execute(
            """
            SELECT se.embedding, se.series_nm
            FROM vod_series_embedding se
            JOIN vod v ON COALESCE(v.series_nm, v.asset_nm) = se.series_nm
            WHERE v.full_asset_id = %s
            LIMIT 1
            """,
            (vod_id,),
        )
        row = cur.fetchone()
        if row is None:
            return []

        query_vec, source_series = row

        cur.execute("SET ivfflat.probes = %(probes)s", {"probes": probes})
        cur.execute(
            """
            SELECT representative_vod_id,
                   1 - (embedding <=> %s::vector) AS content_score
            FROM vod_series_embedding
            WHERE series_nm != %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vec, source_series, query_vec, top_n),
        )
        return [{"vod_id": r[0], "content_score": float(r[1])} for r in cur.fetchall()]


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
content_searcher = ContentSearcher()
load_config = VectorSearchBase.load_config
get_similar_by_meta = content_searcher.search
