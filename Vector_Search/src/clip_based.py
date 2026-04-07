"""CLIP 벡터 기반 유사 VOD 검색."""

from Vector_Search.src.base import VectorSearchBase


class ClipSearcher(VectorSearchBase):
    """CLIP 512차원 벡터 기반 유사 VOD 검색."""

    def search(self, vod_id: str, conn, top_n: int = None) -> list[dict]:
        """CLIP 벡터 기반 유사 VOD TOP-N 반환.

        반환: [{"vod_id": str, "clip_score": float}, ...]
        vod_embedding 미적재 VOD (~30%): 빈 리스트 반환 → 앙상블에서 content_score 100% 반영
        """
        config = self.load_config()
        if top_n is None:
            top_n = config["ensemble"]["top_n"]
        probes = config["search"]["clip_ivfflat_probes"]
        clip_model = config["search"]["clip_model"]

        cur = conn.cursor()

        cur.execute(
            "SELECT embedding FROM vod_embedding WHERE vod_id_fk = %s AND model_name = %s",
            (vod_id, clip_model)
        )
        row = cur.fetchone()
        if row is None:
            return []

        query_vec = row[0]

        cur.execute("SET ivfflat.probes = %(probes)s", {"probes": probes})
        cur.execute(
            """
            SELECT vod_id_fk,
                   1 - (embedding <=> %s::vector) AS clip_score
            FROM vod_embedding
            WHERE vod_id_fk != %s
              AND model_name = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (query_vec, vod_id, clip_model, query_vec, top_n)
        )
        return [{"vod_id": r[0], "clip_score": float(r[1])} for r in cur.fetchall()]


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
clip_searcher = ClipSearcher()
load_config = VectorSearchBase.load_config
get_similar_by_clip = clip_searcher.search
