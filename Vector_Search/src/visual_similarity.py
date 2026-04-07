"""유저 CLIP 임베딩 기반 시각 유사도 VOD 추천.

user_embedding(896D)의 CLIP 부분([:512])과 VOD CLIP 벡터 간
코사인 유사도를 계산하여 유저별 시각적으로 유사한 VOD를 추천한다.

결과는 serving.vod_recommendation에
recommendation_type='VISUAL_SIMILARITY', source_vod_id=NULL로 적재된다.
"""

import numpy as np

from Vector_Search.src.base import VectorSearchBase


class VisualSimilarity(VectorSearchBase):
    """user_embedding CLIP 부분([:512])과 VOD CLIP 벡터 간 코사인 유사도."""

    CLIP_DIM = 512

    @staticmethod
    def extract_clip_vector(embedding_896d):
        """896D user_embedding에서 CLIP 512D 부분 추출."""
        return np.asarray(embedding_896d[:VisualSimilarity.CLIP_DIM], dtype=np.float32)

    def search(self, user_id: str, conn, top_n: int = None) -> list[dict]:
        """단건 유저 기반 시각 유사 VOD TOP-N 반환.

        Args:
            user_id: user_embedding.user_id_fk
            conn: pgvector 등록된 psycopg2 연결
            top_n: 반환 건수 (None이면 config 기본값)

        Returns:
            [{"vod_id": str, "score": float}, ...]
            user_embedding 미적재 유저: 빈 리스트
        """
        config = self.load_config()
        vs_config = config["visual_similarity"]
        if top_n is None:
            top_n = vs_config["top_n"]
        probes = config["search"]["clip_ivfflat_probes"]
        clip_model = config["search"]["clip_model"]

        cur = conn.cursor()

        # 1) user_embedding 조회 → CLIP 512D 추출
        cur.execute(
            "SELECT embedding FROM user_embedding WHERE user_id_fk = %s",
            (user_id,),
        )
        row = cur.fetchone()
        if row is None:
            return []

        user_clip = self.extract_clip_vector(row[0])
        norm = np.linalg.norm(user_clip)
        if norm < 1e-9:
            return []
        user_clip = user_clip / norm

        # 2) 시청 이력 조회 (제외 대상)
        cur.execute(
            "SELECT vod_id_fk FROM watch_history WHERE user_id_fk = %s",
            (user_id,),
        )
        watched = {r[0] for r in cur.fetchall()}

        # 3) 시리즈 대표 VOD의 CLIP 벡터 대상 코사인 유사도 검색
        cur.execute("SET ivfflat.probes = %(probes)s", {"probes": probes})

        # watched 목록이 크면 SQL IN절 대신 후처리 필터 사용
        fetch_n = top_n + len(watched)
        cur.execute(
            """
            SELECT ve.vod_id_fk,
                   1 - (ve.embedding <=> %s::vector) AS score
            FROM vod_embedding ve
            JOIN vod_series_embedding se
              ON ve.vod_id_fk = se.representative_vod_id
            WHERE ve.model_name = %s
            ORDER BY ve.embedding <=> %s::vector
            LIMIT %s
            """,
            (user_clip.tolist(), clip_model, user_clip.tolist(), fetch_n),
        )

        results = []
        for vod_id, score in cur.fetchall():
            if vod_id in watched:
                continue
            results.append({"vod_id": vod_id, "score": round(float(score), 6)})
            if len(results) >= top_n:
                break

        return results


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
visual_similarity = VisualSimilarity()
load_config = VectorSearchBase.load_config
get_visual_recommendations = visual_similarity.search
