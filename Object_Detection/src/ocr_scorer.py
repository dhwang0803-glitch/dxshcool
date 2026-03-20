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

        Args:
            frame: BGR numpy array

        Returns:
            추출된 텍스트 전체 (예: "크림파스타 맛있겠다 tvN")
        """
        results = self._reader.readtext(frame, detail=0)
        return " ".join(results)

    def extract_texts(
        self,
        frames: list[np.ndarray],
        timestamps: list[float],
        sample_interval: int = 3,
    ) -> list[dict]:
        """
        여러 프레임에서 OCR 추출. 매 프레임 하면 느리니까 N프레임마다 샘플링.

        Args:
            frames: BGR 프레임 리스트
            timestamps: 프레임별 타임스탬프
            sample_interval: N프레임마다 OCR (기본 3 = 3초에 1번)

        Returns:
            [{"frame_ts": float, "text": str}, ...]
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
