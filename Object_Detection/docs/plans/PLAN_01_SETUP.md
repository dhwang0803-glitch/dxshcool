> ✅ **완료** (Phase 1). 최신 플로우 → `docs/MATCHING_FLOW.md`

# PLAN_01 — Object_Detection 환경 설정 및 파일럿

- **브랜치**: Object_Detection
- **Phase**: Phase 3
- **작성일**: 2026-03-14

---

## 목표

YOLO 단독으로 VOD 영상에서 객체를 탐지하고,
**옷 / 음식 / 장소** 3개 카테고리 기준 인식률을 측정하여 조장에게 보고한다.

> "얼마나 되는지 먼저 확인하고, 그 결과로 다음 방향(fine-tuning 등)을 결정한다."

---

## YOLO 버전 선택

| | YOLOv8s | YOLO11s |
|--|---------|---------|
| 출시 | 2023 | 2024.09 |
| API | ultralytics | ultralytics (동일) |
| 성능 | 안정적 | 소폭 향상 |
| 자료 | 풍부 | 적음 |

**채택: YOLO11s** (코드 변경 없이 모델명만 다름, 최신 버전 우선)
→ 비교 실험 시 `YOLOv8s`와 같은 파이프라인으로 병행 가능

---

## 탐지 대상 및 현실적 기대치

### COCO 80종 기준 카테고리별 탐지 가능 범위

| 카테고리 | 탐지 가능 | 탐지 불가 | 예상 인식률 |
|---------|---------|---------|-----------|
| **음식** | apple, banana, pizza, cake, cup, bowl 등 서양 음식 위주 | 김치찌개, 비빔밥, 치킨, 떡볶이 등 한식 | ~40% |
| **옷** | person(사람), handbag, backpack, tie | jacket, coat, dress, 색상/스타일 구분 | ~10% |
| **장소** | 직접 탐지 불가. 객체 조합으로 간접 추론만 가능 (couch+tv→거실, bed→침실) | 카페, 주방, 야외 직접 탐지 | ~20% |
| **가구/가전** | couch, chair, tv, laptop, cell phone, refrigerator 등 | - | ~70% |

> 가구/가전이 홈쇼핑 광고 연계에 가장 유리한 카테고리

---

## 구현 대상

### `src/frame_extractor.py`

```
extract_frames(video_path, fps=1, max_frames=None)
    → (frames: list, timestamps: list[float])
    - cv2.VideoCapture로 영상 열기
    - 1fps 샘플링 (기본값)
    - max_frames 초과 시 균등 샘플링
    - 지원 포맷: .mp4, .avi, .mkv, .webm

list_video_files(input_dir, extensions=None) → list[Path]
```

### `src/detector.py`

```
Detector.__init__(model_name="yolo11s.pt", confidence=0.5, device="cpu")
    - ultralytics.YOLO 로드

Detector.infer(frames, timestamps) → list[dict]
    - 프레임별 YOLO 추론

Detector.to_records(vod_id, results) → list[dict]
    - 출력 스키마: {vod_id, frame_ts, label, confidence, bbox}
    - confidence < 0.5 제거
```

### `scripts/batch_detect.py`

```
CLI:
  --input-dir     VOD 영상 파일 디렉터리
  --output        parquet 경로 (기본: data/vod_detected_object.parquet)
  --model         yolo11s.pt | yolov8s.pt (기본: yolo11s.pt)
  --fps           샘플링 fps (기본: 1)
  --conf          신뢰도 임계값 (기본: 0.5)
  --device        cpu | cuda:0
  --dry-run       파일 목록만 출력
  --limit         처리 수 제한
  --status        진행 상황 확인

체크포인트: data/detect_status.json (재시작 시 완료 VOD 스킵)
```

---

## 파일럿 기준 (10건)

| 항목 | 기준 |
|------|------|
| 처리 속도 | ≤ 60초/건 (CPU) |
| 파이프라인 동작 | parquet 정상 생성 |
| 탐지 결과 | 카테고리별 인식률 수치 출력 |

---

## 인식률 측정 방법

파일럿 완료 후 아래 분석 수행:

```python
import pandas as pd

df = pd.read_parquet("data/vod_detected_object.parquet")

# 카테고리별 탐지 빈도
food_labels = ["apple","banana","orange","pizza","cake","donut","sandwich",
               "hot dog","carrot","broccoli","cup","bowl","bottle"]
cloth_labels = ["person","handbag","backpack","tie","suitcase"]
furniture_labels = ["couch","chair","tv","laptop","cell phone",
                    "refrigerator","dining table","bed","clock","vase"]

print("음식 탐지:", df[df.label.isin(food_labels)].vod_id.nunique(), "건")
print("옷(person포함):", df[df.label.isin(cloth_labels)].vod_id.nunique(), "건")
print("가구/가전:", df[df.label.isin(furniture_labels)].vod_id.nunique(), "건")
print("전체 탐지 라벨 분포:\n", df.label.value_counts().head(20))
```

→ 결과를 `reports/phase1_report.md`에 정리하여 조장 보고

---

## 산출물 스키마 (parquet)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `frame_ts` | float | 프레임 타임스탬프(초) |
| `label` | str | YOLO COCO 클래스명 |
| `confidence` | float | 신뢰도 (0.5 이상) |
| `bbox` | list[float] | [x1, y1, x2, y2] |

---

## Phase 1 완료 기준

- [ ] `src/frame_extractor.py` 구현 + 테스트 PASS
- [ ] `src/detector.py` 구현 + 테스트 PASS
- [ ] `scripts/batch_detect.py` 파일럿 10건 실행 성공
- [ ] `reports/phase1_report.md` — 카테고리별 인식률 수치 포함
- [ ] 조장 보고 후 다음 방향 결정

---

## 다음 방향 (Phase 1 결과 후 결정)

| 결과 | 다음 단계 |
|------|---------|
| 인식률 충분 | Shopping_Ad 연동 (PLAN_02) |
| 한식/의류 인식률 낮음 | fine-tuning 검토 (별도 PLAN) |
| 장소 인식 필요 | scene classification 모듈 추가 (별도 PLAN) |
