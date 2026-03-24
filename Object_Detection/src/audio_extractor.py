"""
audio_extractor.py — VOD 영상 → 오디오 추출

ffmpeg subprocess로 영상에서 16kHz mono WAV 추출.
Whisper 권장 포맷.
"""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path


class AudioExtractor:
    """
    extract(video_path) → 임시 WAV 파일 경로 (str)
    사용 후 직접 삭제 또는 컨텍스트 매니저 활용.
    """

    def extract(self, video_path: str, output_path: str | None = None) -> str:
        """
        Args:
            video_path:  입력 영상 파일 경로
            output_path: 출력 WAV 경로 (None이면 임시 파일 생성)

        Returns:
            WAV 파일 경로 (str)
        """
        if output_path is None:
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            output_path = tmp.name
            tmp.close()

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-ar", "16000",   # 16kHz (Whisper 권장)
            "-ac", "1",       # mono
            "-f", "wav",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg 오디오 추출 실패: {result.stderr.decode(errors='replace')}"
            )
        return output_path
