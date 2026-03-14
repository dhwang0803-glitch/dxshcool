"""
frame_extractor.py — VOD 영상 프레임 추출
"""
import cv2
import numpy as np
from pathlib import Path


SUPPORTED_EXTENSIONS = {".mp4", ".avi", ".mkv", ".webm"}


def extract_frames(video_path: str, fps: float = 1.0, max_frames: int = None):
    """
    영상 파일에서 N fps 간격으로 프레임 추출.

    Returns:
        frames: list of np.ndarray (BGR)
        timestamps: list of float (초 단위)
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"영상을 열 수 없습니다: {video_path}")

    video_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    interval = max(1, int(video_fps / fps))

    # 추출할 프레임 인덱스 계산
    candidate_indices = list(range(0, total_frames, interval))

    # max_frames 제한 — 균등 샘플링
    if max_frames and len(candidate_indices) > max_frames:
        sampled = np.linspace(0, len(candidate_indices) - 1, max_frames, dtype=int)
        candidate_indices = [candidate_indices[i] for i in sampled]

    frames, timestamps = [], []
    for idx in candidate_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ret, frame = cap.read()
        if not ret:
            continue
        ts = idx / video_fps
        frames.append(frame)
        timestamps.append(round(ts, 3))

    cap.release()
    return frames, timestamps


def list_video_files(input_dir: str, extensions: set = None) -> list:
    """
    디렉터리에서 영상 파일 목록 반환.

    Returns:
        list of Path
    """
    exts = extensions or SUPPORTED_EXTENSIONS
    input_path = Path(input_dir)
    files = [f for f in input_path.rglob("*") if f.suffix.lower() in exts]
    return sorted(files)
