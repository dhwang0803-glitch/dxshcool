"""
Phase 1 테스트 — frame_extractor.py + detector.py
TDD Red 단계: 구현 전 먼저 작성
"""
import pytest
import sys
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ─────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    """테스트용 더미 영상 생성 (30프레임, 10fps, 320x240)"""
    import cv2
    tmp = tmp_path_factory.mktemp("videos")
    path = tmp / "test_video.mp4"
    out = cv2.VideoWriter(
        str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240)
    )
    for i in range(30):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        frame[:, :, i % 3] = 100  # 단색 프레임
        out.write(frame)
    out.release()
    return path


@pytest.fixture(scope="session")
def yolo_available():
    try:
        from ultralytics import YOLO
        return True
    except ImportError:
        return False


# ─────────────────────────────────────────
# frame_extractor 테스트
# ─────────────────────────────────────────

def test_P1_01_cv2_import():
    """cv2 설치 확인"""
    import cv2
    assert cv2.__version__


def test_P1_02_ultralytics_import(yolo_available):
    """ultralytics 설치 확인"""
    assert yolo_available, "pip install ultralytics 필요"


def test_P1_03_extract_frames_returns_list(sample_video):
    """extract_frames → (list, list) 반환"""
    from frame_extractor import extract_frames
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    assert isinstance(frames, list)
    assert isinstance(timestamps, list)
    assert len(frames) > 0


def test_P1_04_frames_timestamps_aligned(sample_video):
    """frames, timestamps 길이 일치"""
    from frame_extractor import extract_frames
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    assert len(frames) == len(timestamps)


def test_P1_05_max_frames_limit(sample_video):
    """max_frames 제한 적용"""
    from frame_extractor import extract_frames
    frames, _ = extract_frames(str(sample_video), fps=10, max_frames=5)
    assert len(frames) <= 5


def test_P1_06_invalid_video_raises():
    """존재하지 않는 영상 → ValueError"""
    from frame_extractor import extract_frames
    with pytest.raises((ValueError, Exception)):
        extract_frames("nonexistent.mp4", fps=1)


def test_P1_07_list_video_files(tmp_path):
    """list_video_files → mp4 파일 목록 반환"""
    from frame_extractor import list_video_files
    (tmp_path / "a.mp4").touch()
    (tmp_path / "b.mp4").touch()
    (tmp_path / "c.txt").touch()
    files = list_video_files(str(tmp_path))
    assert len(files) == 2
    assert all(f.suffix == ".mp4" for f in files)


def test_P1_08_list_video_files_empty(tmp_path):
    """영상 없는 디렉터리 → 빈 리스트 (예외 X)"""
    from frame_extractor import list_video_files
    files = list_video_files(str(tmp_path))
    assert files == []


# ─────────────────────────────────────────
# detector 테스트
# ─────────────────────────────────────────

def test_P1_09_detector_init(yolo_available):
    """Detector 초기화"""
    if not yolo_available:
        pytest.skip("ultralytics 미설치")
    from detector import Detector
    det = Detector(model_name="yolo11n.pt", device="cpu")
    assert det is not None


def test_P1_10_infer_returns_list(sample_video, yolo_available):
    """infer → list 반환"""
    if not yolo_available:
        pytest.skip("ultralytics 미설치")
    from frame_extractor import extract_frames
    from detector import Detector
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    det = Detector(model_name="yolo11n.pt", device="cpu")
    results = det.infer(frames, timestamps)
    assert isinstance(results, list)


def test_P1_11_to_records_schema(sample_video, yolo_available):
    """to_records → 5개 컬럼 스키마"""
    if not yolo_available:
        pytest.skip("ultralytics 미설치")
    from frame_extractor import extract_frames
    from detector import Detector
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    det = Detector(model_name="yolo11n.pt", device="cpu")
    records = det.to_records("test_vod", det.infer(frames, timestamps))
    assert isinstance(records, list)
    for r in records:
        assert set(r.keys()) >= {"vod_id", "frame_ts", "label", "confidence", "bbox"}


def test_P1_12_confidence_filter(sample_video, yolo_available):
    """confidence < 0.5 제거"""
    if not yolo_available:
        pytest.skip("ultralytics 미설치")
    from frame_extractor import extract_frames
    from detector import Detector
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    det = Detector(model_name="yolo11n.pt", confidence=0.5, device="cpu")
    records = det.to_records("test_vod", det.infer(frames, timestamps))
    for r in records:
        assert r["confidence"] >= 0.5


def test_P1_13_parquet_save(sample_video, yolo_available, tmp_path):
    """parquet 저장 및 컬럼 검증"""
    if not yolo_available:
        pytest.skip("ultralytics 미설치")
    import pandas as pd
    from frame_extractor import extract_frames
    from detector import Detector
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    det = Detector(model_name="yolo11n.pt", device="cpu")
    records = det.to_records("test_vod", det.infer(frames, timestamps))
    out = tmp_path / "out.parquet"
    df = pd.DataFrame(records) if records else pd.DataFrame(
        columns=["vod_id", "frame_ts", "label", "confidence", "bbox"]
    )
    df.to_parquet(str(out), index=False)
    df2 = pd.read_parquet(str(out))
    for col in ["vod_id", "frame_ts", "label", "confidence", "bbox"]:
        assert col in df2.columns
