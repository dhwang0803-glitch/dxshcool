# Phase 5 계획 — YOLOv11 파인튜닝 고도화

- **브랜치**: Object_Detection
- **작성일**: 2026-03-16
- **작성자**: 박아름
- **참조**: 조장(황대원) 제안 (YoLov11_파인튜닝.txt)
- **선행 조건**: Phase 4 완료 (51/51 PASS), PR #31 머지, Shopping_Ad 연동 완료

---

## 배경

Phase 1 파일럿에서 확인된 구조적 한계:

> YOLO11s (COCO 80종)는 한식(비빔밥, 김치찌개, 굴비 등) 탐지 0건.
> COCO 데이터셋이 서양 음식 중심으로 구성되어 있어 한국 VOD 도메인에 적용 시 음식 카테고리 커버리지 부족.

Phase 2~4에서 CLIP zero-shot + Whisper STT로 우회 구현을 완료했으나,
bbox 정밀도와 한식 직접 탐지 정확도 측면에서 파인튜닝이 장기적으로 우위를 가진다.
조장 제안을 바탕으로 Phase 5에서 YOLO 파인튜닝을 적용하는 방향을 검토한다.

---

## 방식 비교: 파인튜닝 vs 현재 구현

### 조장 제안: YOLOv11 파인튜닝

AI Hub '음식 이미지 및 외식 산업 데이터'로 라벨링 후 재학습.
한국 음식 클래스를 YOLO가 직접 bbox로 탐지하도록 모델을 커스텀화한다.

### 현재 구현: YOLO + CLIP + STT 멀티모달

한식 탐지 불가 문제를 우회하는 방식:
- CLIP zero-shot: 프레임 전체 의미 유사도로 "굴비 먹는 식사 장면" 탐지
- Whisper STT: 대사에서 "영광 굴비", "한우" 등 키워드 직접 추출

---

## 핵심 트레이드오프

| 비교 항목 | 조장 제안 (파인튜닝) | 현재 구현 (CLIP+STT) |
|---------|-----------------|-------------------|
| 구현 비용 | 높음 — 데이터 수집·라벨링·학습 필요 | 완료 ✅ |
| 한식 탐지 정확도 | 높음 — bbox 정밀 탐지 | CLIP은 프레임 전체 의미 (bbox 없음) |
| 확장성 | 낮음 — 클래스 추가 시 재학습 필요 | 높음 — yaml 쿼리 추가만으로 확장 |
| 장소/맥락 탐지 | 불가 (YOLO는 객체 탐지 전용) | CLIP으로 가능 (바닷가, 전통시장 등) |
| STT 대사 커버 | 없음 | Whisper로 발화 키워드 추출 |
| 오탐 방지 | 모델 학습에 의존 | context_filter 레이어로 명시적 차단 |
| Shopping_Ad 연동 | bbox 기반 정밀 매핑 가능 | context_valid=True 레코드 조인 |
| 도메인 갭 위험 | 있음 — AI Hub(정지 이미지) vs VOD 프레임(블러·편집) | 없음 — 쿼리 기반 |

---

## 결론: 두 방식은 경쟁이 아니라 보완 관계

현재 구현과 파인튜닝은 파이프라인 레이어가 다르다.

```
[Phase 5 파인튜닝 적용 후 구조]

VOD 영상
│
├── YOLO (파인튜닝 모델)
│     → 한식 포함 커스텀 클래스 bbox 탐지
│     → vod_detected_object.parquet (label 커버리지 확장)
│
├── CLIP (현재 유지)
│     → 장소/맥락/여행지 등 YOLO 비탐지 개념 보완
│     → vod_clip_concept.parquet
│
└── STT (현재 유지)
      → 발화 키워드 직접 추출
      → vod_stt_concept.parquet
```

파인튜닝 완료 시 `src/detector.py`의 모델 경로만 교체하면 됨.
CLIP, STT, context_filter는 수정 없이 유지된다.

---

## Phase 5 구현 계획

### 전제 조건

- [ ] PR #31 머지 완료
- [ ] Shopping_Ad 연동 완료 (현재 파이프라인 검증 후 진행)

---

### Step 1 — 데이터 수집

**AI Hub** '음식 이미지 및 외식 산업 데이터' 활용:
- URL: https://www.aihub.or.kr (음식 카테고리 검색)
- 제공 포맷: 이미지 + 라벨링 JSON (COCO 형식 변환 필요)
- 권장 클래스: 한식 중심 10~20종 (Phase 1 탐지 0건 항목 우선)

| 우선순위 클래스 | Phase 1 현황 | 파인튜닝 기대 효과 |
|-------------|------------|----------------|
| 비빔밥 | 탐지 0건 | 직접 bbox 탐지 |
| 김치찌개/된장찌개 | 탐지 0건 | 직접 bbox 탐지 |
| 굴비/생선구이 | 탐지 0건 | STT 보완 대폭 축소 |
| 대게/새우 | 탐지 0건 | 지방특산물 정밀도 향상 |
| 한우/삼겹살 | 탐지 0건 | 고기구이 카테고리 직접 탐지 |

> **도메인 갭 주의**: AI Hub 데이터(정지 이미지)만으로 학습 시 예능 VOD 프레임(움직임 블러, 클로즈업 편집, 자막 오버레이)과 갭 발생 가능.
> `VOD_Embedding/data/trailers_아름`에서 추출한 실제 VOD 프레임을 학습 데이터에 **반드시 포함**할 것.

---

### Step 2 — 라벨링

**권장 도구**:

| 도구 | 특징 | 권장 용도 |
|------|------|---------|
| **CVAT** | VOD 파일 직접 업로드 → 프레임별 라벨링 | VOD 프레임 라벨링 (필수) |
| **Roboflow** | 웹 기반 협업, YOLOv11 형식 바로 내보내기 | AI Hub 데이터 변환 + 팀 협업 |

**라벨 형식** (YOLOv11 표준):
```
# {class_id} {x_center} {y_center} {width} {height} (0~1 정규화)
0 0.5 0.5 0.2 0.3
```

**데이터셋 폴더 구조**:
```
Object_Detection/data/finetune_dataset/
├── train/
│   ├── images/   ← AI Hub + trailers_아름 프레임 혼합
│   └── labels/   ← YOLO 형식 .txt
├── val/
│   ├── images/
│   └── labels/
└── data.yaml
```

**`data.yaml` 예시**:
```yaml
train: ../train/images
val: ../val/images

nc: 10
names:
  - 비빔밥
  - 김치찌개
  - 된장찌개
  - 굴비
  - 대게
  - 한우
  - 삼겹살
  - 전복
  - 장어
  - 해산물_일반
```

---

### Step 3 — 파인튜닝 학습

```python
from ultralytics import YOLO

# 기존 yolo11s.pt에서 전이학습 (Transfer Learning)
model = YOLO("yolo11s.pt")

model.train(
    data="Object_Detection/data/finetune_dataset/data.yaml",
    epochs=100,
    imgsz=640,
    device=0,        # GPU 필수 권장 (CPU는 수일 소요)
    batch=16,
    patience=20,     # Early stopping
    project="Object_Detection/data/runs",
    name="korean_food_v1"
)

metrics = model.val()
```

> **GPU 환경 필수**: CPU 학습은 epoch당 수 시간 소요. VPC GPU 인스턴스 또는 로컬 GPU 사용 권장.

---

### Step 4 — 파이프라인 교체

파인튜닝 완료 후 `config/detection_config.yaml`만 수정하면 됨:

```yaml
# 기존
model: yolo11s.pt

# Phase 5 교체
model: Object_Detection/data/runs/korean_food_v1/weights/best.pt
```

`src/detector.py`, `scripts/batch_detect.py` 코드 수정 불필요.

---

### Step 5 — 검증 및 A/B 비교

| 검증 항목 | 기준 |
|---------|------|
| mAP@0.5 | 기존 COCO 모델 대비 한식 카테고리 mAP 향상 |
| 파이프라인 PASS | `tests/test_phase1_setup.py` 13/13 유지 |
| CLIP 보완 효과 | 파인튜닝 탐지 + CLIP 보완 시 광고 트리거 증가율 |
| STT 키워드 감소 | 시각 탐지 커버 증가 → STT 의존도 감소 확인 |

**A/B 비교 방법**:
```python
# 동일 10 VOD 대상
# A: 기존 yolo11s.pt
# B: 파인튜닝 best.pt
# 비교 지표: 한식 라벨 탐지 건수, context_valid=True 비율
```

---

## 완료 기준

- [ ] 커스텀 데이터셋 준비 (AI Hub + VOD 프레임 혼합, 클래스별 최소 500장)
- [ ] 라벨링 완료 (CVAT 또는 Roboflow)
- [ ] `model.train()` 학습 완료 (mAP@0.5 ≥ 0.6 목표)
- [ ] `config/detection_config.yaml` 모델 경로 교체
- [ ] `tests/test_phase1_setup.py` 13/13 PASS 유지
- [ ] CLIP + STT 파이프라인 영향 없음 확인
- [ ] A/B 비교 결과 리포트 작성

---

## 기대 효과

| 항목 | Phase 4 현재 | Phase 5 이후 |
|------|------------|------------|
| 한식 탐지 | CLIP 우회 (프레임 전체) | YOLO bbox 직접 탐지 |
| 지방특산물 정밀도 | STT 의존 (recall 낮음) | 시각 탐지 + STT 이중 확인 |
| context_filter 효과 | 식기류 체크 + CLIP negative | YOLO 한식 bbox + 식기류 동반 확인 |
| Shopping_Ad 연동 | concept 기반 매칭 | bbox 좌표 기반 정밀 매칭 가능 |
