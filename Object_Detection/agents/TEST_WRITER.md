# Test Writer Agent — Object_Detection

## 역할
구현 전에 실패하는 테스트를 먼저 작성한다 (TDD Red 단계).
구현 후에는 테스트를 실행하고 결과를 수집한다 (검증 단계).

---

## 테스트 파일 위치

| Phase | 테스트 파일 |
|-------|-----------|
| Phase 1 | `Object_Detection/tests/test_phase1_setup.py` |
| Phase 2 | `Object_Detection/tests/test_phase2_batch.py` |
| Phase 3 | `Object_Detection/tests/test_phase3_ingest.py` |

---

## 테스트 작성 원칙

1. 구현 코드가 없어도 테스트를 먼저 작성한다
2. 각 테스트는 하나의 요구사항만 검증한다
3. 외부 의존성(영상 파일, GPU)은 픽스처로 추상화한다
4. 실제 모델 추론은 `@pytest.mark.slow`로 분리 — 기본 실행에서 제외 가능

---

## 테스트 작성 형식

```python
import pytest
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ─────────────────────────────────────────
# 픽스처
# ─────────────────────────────────────────

@pytest.fixture(scope="session")
def sample_video(tmp_path_factory):
    """테스트용 더미 영상 생성 (cv2 없이도 파일 존재 확인용)"""
    import cv2, numpy as np
    tmp = tmp_path_factory.mktemp("videos")
    path = tmp / "test_video.mp4"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10, (320, 240))
    for _ in range(30):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        out.write(frame)
    out.release()
    return path

@pytest.fixture(scope="session")
def yolo_model_available():
    """YOLOv8 모델 파일 또는 ultralytics 패키지 존재 여부"""
    try:
        from ultralytics import YOLO
        return True
    except ImportError:
        return False

# ─────────────────────────────────────────
# Phase 1 필수 테스트 항목
# ─────────────────────────────────────────

def test_P1_01_cv2_import():
    """cv2 설치 확인"""
    import cv2
    assert cv2.__version__, "cv2 미설치"

def test_P1_02_ultralytics_import(yolo_model_available):
    """ultralytics 설치 확인"""
    assert yolo_model_available, "ultralytics 미설치 — pip install ultralytics"

def test_P1_03_extract_frames_returns_list(sample_video):
    """extract_frames가 프레임 리스트 반환"""
    from frame_extractor import extract_frames
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    assert isinstance(frames, list), "frames가 list가 아님"
    assert isinstance(timestamps, list), "timestamps가 list가 아님"
    assert len(frames) > 0, "프레임이 0개"

def test_P1_04_extract_frames_timestamp_alignment(sample_video):
    """frames와 timestamps 길이 일치"""
    from frame_extractor import extract_frames
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    assert len(frames) == len(timestamps), "frames/timestamps 길이 불일치"

def test_P1_05_extract_frames_max_limit(sample_video):
    """max_frames 제한 적용"""
    from frame_extractor import extract_frames
    frames, _ = extract_frames(str(sample_video), fps=10, max_frames=5)
    assert len(frames) <= 5, f"max_frames=5인데 {len(frames)}개 반환"

def test_P1_06_detector_init(yolo_model_available):
    """Detector 초기화 (모델 로드)"""
    if not yolo_model_available:
        pytest.skip("ultralytics 미설치")
    from detector import Detector
    det = Detector(model_name="yolov8n", device="cpu")
    assert det is not None

def test_P1_07_detector_infer_returns_records(sample_video, yolo_model_available):
    """Detector.infer 결과가 list[dict] 형태"""
    if not yolo_model_available:
        pytest.skip("ultralytics 미설치")
    from frame_extractor import extract_frames
    from detector import Detector
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    det = Detector(model_name="yolov8n", device="cpu")
    records = det.to_records("test_vod_id", det.infer(frames, timestamps))
    assert isinstance(records, list), "records가 list가 아님"
    for r in records:
        assert "vod_id" in r
        assert "frame_ts" in r
        assert "label" in r
        assert "confidence" in r
        assert "bbox" in r

def test_P1_08_detector_confidence_filter(sample_video, yolo_model_available):
    """신뢰도 0.5 미만 객체 제거"""
    if not yolo_model_available:
        pytest.skip("ultralytics 미설치")
    from frame_extractor import extract_frames
    from detector import Detector
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    det = Detector(model_name="yolov8n", confidence=0.5, device="cpu")
    records = det.to_records("vod_test", det.infer(frames, timestamps))
    for r in records:
        assert r["confidence"] >= 0.5, f"신뢰도 {r['confidence']} < 0.5"

def test_P1_09_parquet_schema(sample_video, yolo_model_available, tmp_path):
    """parquet 파일 컬럼 스키마 검증"""
    if not yolo_model_available:
        pytest.skip("ultralytics 미설치")
    import pandas as pd
    from frame_extractor import extract_frames
    from detector import Detector
    frames, timestamps = extract_frames(str(sample_video), fps=1)
    det = Detector(model_name="yolov8n", device="cpu")
    records = det.to_records("vod_test", det.infer(frames, timestamps))
    out_path = tmp_path / "test_output.parquet"
    df = pd.DataFrame(records) if records else pd.DataFrame(
        columns=["vod_id", "frame_ts", "label", "confidence", "bbox"]
    )
    df.to_parquet(str(out_path), index=False)
    df_read = pd.read_parquet(str(out_path))
    for col in ["vod_id", "frame_ts", "label", "confidence", "bbox"]:
        assert col in df_read.columns, f"컬럼 '{col}' 누락"
```

---

## Phase 1 필수 테스트 항목 요약

| ID | 항목 | 기준 |
|----|------|------|
| P1-01 | cv2 설치 | import 성공 |
| P1-02 | ultralytics 설치 | import 성공 |
| P1-03 | extract_frames 반환 타입 | list, len > 0 |
| P1-04 | frames/timestamps 길이 일치 | len 동일 |
| P1-05 | max_frames 제한 | len ≤ max_frames |
| P1-06 | Detector 초기화 | 예외 없음 |
| P1-07 | infer 결과 스키마 | 5개 컬럼 존재 |
| P1-08 | 신뢰도 필터 | confidence ≥ 0.5 |
| P1-09 | parquet 컬럼 스키마 | 5개 컬럼 일치 |

---

## 테스트 결과 수집 형식

```
전체 테스트: X건
PASS: X건
FAIL: X건
SKIP: X건 (ultralytics 미설치 등)
오류율: X%

FAIL 목록:
- [테스트 ID]: [실패 메시지]
```
