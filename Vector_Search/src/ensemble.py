"""CLIP + 메타데이터 벡터 앙상블 스코어링."""

from Vector_Search.src.base import VectorSearchBase


class EnsembleScorer(VectorSearchBase):
    """두 검색 엔진의 스코어를 앙상블."""

    @staticmethod
    def score(
        clip_results: list[dict],
        content_results: list[dict],
        alpha: float = None,
        top_n: int = None,
    ) -> list[dict]:
        """두 결과를 vod_id 기준으로 합산 후 내림차순 정렬.

        clip_score 없는 경우(vod_embedding 미적재 ~30%): alpha=0으로 처리 → content_score 100% 반영.
        content_score 없는 경우: 0으로 처리.
        """
        config = VectorSearchBase.load_config()
        if alpha is None:
            alpha = config["ensemble"]["alpha"]
        if top_n is None:
            top_n = config["ensemble"]["top_n"]

        scores = {}

        for r in clip_results:
            scores.setdefault(r["vod_id"], {"clip_score": 0.0, "content_score": 0.0})
            scores[r["vod_id"]]["clip_score"] = r["clip_score"]

        for r in content_results:
            scores.setdefault(r["vod_id"], {"clip_score": 0.0, "content_score": 0.0})
            scores[r["vod_id"]]["content_score"] = r["content_score"]

        results = []
        for vod_id, s in scores.items():
            effective_alpha = alpha if s["clip_score"] > 0.0 else 0.0
            final = effective_alpha * s["clip_score"] + (1 - effective_alpha) * s["content_score"]
            results.append({
                "vod_id": vod_id,
                "final_score": round(final, 6),
                "clip_score": s["clip_score"],
                "content_score": s["content_score"],
            })

        return sorted(results, key=lambda x: x["final_score"], reverse=True)[:top_n]


# ── 모듈 레벨 싱글턴 + 하위 호환 별칭 ──────────────────────────────────────
ensemble_scorer = EnsembleScorer()
load_config = VectorSearchBase.load_config
ensemble_scores = EnsembleScorer.score
