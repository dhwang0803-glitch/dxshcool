"""
stt_scorer.py — Whisper STT 래퍼

VOD 오디오 파일 → transcript + 구간 타임스탬프 리스트.
"""
from __future__ import annotations


class SttScorer:
    """
    transcribe(audio_path) → list of {start, end, text}
    """

    def __init__(self, model_name: str = "small"):
        import whisper
        self._model = whisper.load_model(model_name)

    def transcribe(self, audio_path: str) -> list[dict]:
        """
        오디오 파일 → 구간별 transcript 리스트.

        Args:
            audio_path: 16kHz mono WAV 경로

        Returns:
            [{"start": float, "end": float, "text": str}, ...]
        """
        result = self._model.transcribe(
            audio_path,
            language="ko",
            verbose=False,
        )
        return [
            {
                "start": seg["start"],
                "end":   seg["end"],
                "text":  seg["text"].strip(),
            }
            for seg in result.get("segments", [])
        ]
