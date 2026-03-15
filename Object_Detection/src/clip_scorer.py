"""
clip_scorer.py — CLIP Zero-shot 프레임 개념 스코어링

YOLO가 못 잡는 장면/개념(바닷가, 한식, 시장 등)을
텍스트 쿼리 유사도로 보완한다.

역할: 보완용 / 장면 의미 실험용
한계: bbox 없음, 정밀 탐지 아님, 지역성 단독 해결 불가
"""
from __future__ import annotations
import numpy as np
from PIL import Image


class ClipScorer:
    def __init__(self, model_name: str = "clip-ViT-B-32"):
        from sentence_transformers import SentenceTransformer
        try:
            self.model = SentenceTransformer(model_name)
        except Exception:
            fallback = "sentence-transformers/clip-ViT-B-32-multilingual-v1"
            self.model = SentenceTransformer(fallback)

    def _frame_to_pil(self, frame: np.ndarray) -> Image.Image:
        import cv2
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def score_frame(self, frame: np.ndarray, queries: list[str]) -> dict[str, float]:
        """
        단일 프레임 + 쿼리 리스트 → 쿼리별 유사도 점수 dict.

        Returns:
            {"바닷가": 0.31, "주방": 0.18, ...}
        """
        if not queries:
            return {}

        pil = self._frame_to_pil(frame)
        img_emb = self.model.encode(pil, convert_to_numpy=True)
        txt_emb = self.model.encode(queries, convert_to_numpy=True)

        # 코사인 유사도
        img_norm = img_emb / (np.linalg.norm(img_emb) + 1e-8)
        txt_norm = txt_emb / (np.linalg.norm(txt_emb, axis=1, keepdims=True) + 1e-8)
        scores = (txt_norm @ img_norm).tolist()

        # 0~1 클리핑 (코사인은 -1~1이지만 CLIP 실무 범위는 0~1)
        return {q: float(max(0.0, min(1.0, s))) for q, s in zip(queries, scores)}

    def score_frames(self, frames: list[np.ndarray], queries: list[str]) -> list[dict[str, float]]:
        """
        여러 프레임 배치 처리 → 프레임별 score dict 리스트.
        """
        return [self.score_frame(f, queries) for f in frames]

    def to_records(
        self,
        vod_id: str,
        timestamps: list[float],
        results: list[dict[str, float]],
        threshold: float = 0.22,
        query_category_map: dict[str, str] | None = None,
    ) -> list[dict]:
        """
        score_frames 결과 → parquet 행 리스트.
        threshold 미만 제거. negative 카테고리 제거.

        Args:
            query_category_map: {"쿼리": "카테고리"} — ad_category 컬럼 부여용.
                                 "negative" 카테고리는 records에서 제외.

        Returns:
            list of {"vod_id", "frame_ts", "concept", "clip_score", "ad_category"}
        """
        records = []
        for ts, scores in zip(timestamps, results):
            for concept, score in scores.items():
                if score < threshold:
                    continue
                ad_category = query_category_map.get(concept, "") if query_category_map else ""
                if ad_category == "negative":
                    continue
                records.append({
                    "vod_id":      vod_id,
                    "frame_ts":    ts,
                    "concept":     concept,
                    "clip_score":  round(score, 4),
                    "ad_category": ad_category,
                })
        return records
