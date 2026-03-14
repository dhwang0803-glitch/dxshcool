# PLAN_01 — Object_Detection 환경 설정 및 파일럿

- **브랜치**: Object_Detection
- **Phase**: Phase 3
- **작성일**: 2026-03-14

---

## 목표

YOLOv8 기반 VOD 배치 사물인식 파이프라인을 구축하고,
파일럿(소규모 VOD 샘플)으로 동작 및 품질을 검증한다.

---

## 구현 대상

### Phase 1 — 프레임 추출 (`src/frame_extractor.py`)

| 함수 | 설명 |
|------|------|
| `extract_frames(video_path, fps, max_frames)` | 영상 파일 → 프레임 배열 + 타임스탬프 반환 |
| `list_video_files(input_dir)` | 디렉터리에서 영상 파일 목록 반환 |

요구사항:
- `cv2.VideoCapture`로 영상 열기
- N fps 샘플링 (1fps 기본값)
- `max_frames` 초과 시 균등 샘플링으로 대체
- 지원 포맷: `.mp4`, `.avi`, `.mkv`, `.webm`

---

### Phase 2 — YOLOv8 추론 (`src/detector.py`)

| 함수/클래스 | 설명 |
|------------|------|
| `Detector.__init__(config)` | 모델 로드, device 설정 |
| `Detector.infer(frames, timestamps)` | 프레임 배열 → 검출 결과 리스트 반환 |
| `Detector.to_records(vod_id, results)` | 검출 결과 → parquet 행 리스트 변환 |

출력 스키마:
```python
{
    "vod_id": str,        # full_asset_id
    "frame_ts": float,    # 타임스탬프(초)
    "label": str,         # COCO 클래스명
    "confidence": float,  # 0.5 이상만 포함
    "bbox": list[float],  # [x1, y1, x2, y2]
}
```

---

### Phase 3 — 배치 실행 (`scripts/batch_detect.py`)

```
대상 영상 파일 목록 로드
    → VOD별 루프
    → frame_extractor.extract_frames()
    → detector.infer()
    → detector.to_records()
    → 누적 후 batch_save_interval마다 parquet append
    → detect_status.json 체크포인트 저장
```

CLI 인터페이스:
```bash
python scripts/batch_detect.py \
    --input-dir /path/to/videos \
    --output data/vod_detected_object.parquet \
    [--model yolov8s] \
    [--fps 1] \
    [--conf 0.5] \
    [--dry-run] \
    [--limit 5] \
    [--status]
```

---

## 파일럿 기준

| 항목 | 기준 |
|------|------|
| 테스트 영상 | 10건 (장르 혼합) |
| 처리 속도 | ≤ 60초/건 (CPU 기준) |
| 검출 성공률 | ≥ 1개 이상 객체 검출 비율 80% |
| parquet 정합성 | 컬럼 타입 일치, null 없음 |

---

## 사전 조건

- [ ] `myenv`에 `ultralytics`, `opencv-python-headless`, `pandas` 설치
- [ ] 테스트용 VOD 영상 파일 확보 (로컬)
- [ ] `config/detection_config.yaml` 경로 설정 확인

---

## 다음 단계 (PLAN_02 예정)

- 전체 VOD 배치 실행 (batch_detect.py 대규모)
- Shopping_Ad 파이프라인과 parquet 인터페이스 연동 확인
- `public.detected_objects` 테이블 스키마 Database_Design과 협의
- DB 적재 스크립트 (`scripts/ingest_to_db.py`) 구현
