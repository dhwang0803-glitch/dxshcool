"""
ocr_scorer.py — 프레임 자막 OCR 텍스트 추출

예능 자막에서 음식명/장소명을 추출하여 STT를 보완한다.
화면에 "크림파스타", "남원 추어탕" 등 자막이 있으면 잡을 수 있음.

역할: STT 보완 — 출연자가 말 안 해도 자막에 있으면 잡음
"""
from __future__ import annotations
import numpy as np


class OcrScorer:
    def __init__(self, langs: list[str] = None):
        import easyocr
        if langs is None:
            langs = ["ko", "en"]
        self._reader = easyocr.Reader(langs, gpu=False, verbose=False)

    def extract_text(self, frame: np.ndarray) -> str:
        """
        단일 프레임 → OCR 텍스트 (공백으로 이어붙임).
        기존 호환용 (pilot_multimodal_test.py 등).
        """
        results = self._reader.readtext(frame, detail=0)
        return " ".join(results)

    def extract_detail(self, frame: np.ndarray) -> list[dict]:
        """
        단일 프레임 → OCR 상세 결과 (텍스트 + bbox + confidence).

        Returns:
            [{"text": str, "confidence": float, "bbox": [x1,y1,x2,y2]}, ...]
        """
        results = self._reader.readtext(frame, detail=1)
        details = []
        for bbox_points, text, conf in results:
            if not text.strip():
                continue
            # EasyOCR bbox: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]] → [x1,y1,x2,y2]
            xs = [p[0] for p in bbox_points]
            ys = [p[1] for p in bbox_points]
            details.append({
                "text": text.strip(),
                "confidence": round(float(conf), 4),
                "bbox": [round(min(xs), 2), round(min(ys), 2),
                         round(max(xs), 2), round(max(ys), 2)],
            })
        return details

    def extract_texts(
        self,
        frames: list[np.ndarray],
        timestamps: list[float],
        sample_interval: int = 3,
    ) -> list[dict]:
        """
        여러 프레임에서 OCR 추출 (텍스트만, 기존 호환).
        """
        results = []
        for i in range(0, len(frames), sample_interval):
            text = self.extract_text(frames[i])
            if text.strip():
                results.append({
                    "frame_ts": timestamps[i],
                    "text": text.strip(),
                })
        return results

    def extract_details(
        self,
        frames: list[np.ndarray],
        timestamps: list[float],
        sample_interval: int = 3,
    ) -> list[dict]:
        """
        여러 프레임에서 OCR 상세 추출 (bbox + confidence 포함).
        배치 파이프라인용 — DB detected_object_ocr 스키마 매칭.

        Returns:
            [{"frame_ts": float, "text": str, "confidence": float, "bbox": [x1,y1,x2,y2]}, ...]
        """
        results = []
        for i in range(0, len(frames), sample_interval):
            details = self.extract_detail(frames[i])
            for d in details:
                results.append({
                    "frame_ts": timestamps[i],
                    "text": d["text"],
                    "confidence": d["confidence"],
                    "bbox": d["bbox"],
                })
        return results
