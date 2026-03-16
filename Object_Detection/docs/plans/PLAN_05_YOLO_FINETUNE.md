# PLAN_05 — YOLOv11 파인튜닝 (한식 탐지 고도화)

- **브랜치**: Object_Detection
- **Phase**: Phase 5
- **작성일**: 2026-03-16
- **작성자**: 박아름
- **선행 조건**: Phase 4 완료 (51/51 PASS), PR #31 MERGED ✅, Shopping_Ad 연동 완료
- **참조**: 조장(황대원) 제안 (YoLov11_파인튜닝.txt), `docs/reports/phase5_yolo_finetune_plan.md`
- **업데이트**: 2026-03-16 — 조장 Ollama 제안 반영, 4가지 접근 방식 비교 및 구현 우선순위 재정의

---

## 목적

Phase 1 파일럿에서 확인된 구조적 한계를 정공법으로 해결한다.

```
Phase 1 결과: YOLO11s (COCO 80종) 한식 탐지 0건
  → 비빔밥, 김치찌개, 굴비, 대게 등 직접 탐지 불가
  → Phase 2~4에서 CLIP + STT 우회로 보완

Phase 5 목표: 커스텀 한식 클래스를 YOLO가 직접 bbox로 탐지
  → CLIP+STT와 결합하여 전체 파이프라인 정확도 향상
```

---

## 전체 작업 흐름

```
[Step 1] 데이터 수집
    AI Hub 음식 데이터 + trailers_아름 VOD 프레임 혼합
         ↓
[Step 2] 라벨링
    Roboflow (AI Hub 데이터) + CVAT (VOD 프레임)
         ↓
[Step 3] Google Colab Pro — 파인튜닝 학습
    Drive 업로드 → model.train() → best.pt 다운로드
         ↓
[Step 4] 로컬 파이프라인 통합
    best.pt → models/ 저장 → config 경로 교체
         ↓
[Step 5] 검증
    A/B 비교 (기존 yolo11s.pt vs 파인튜닝 best.pt)
    tests/test_phase1_setup.py 13/13 PASS 유지 확인
```

---

## Step 1 — 데이터 수집

### 1-1. AI Hub 공개 데이터

**AI Hub** '음식 이미지 및 외식 산업 데이터' 활용.

- 주소: https://www.aihub.or.kr (음식 카테고리 검색)
- 제공 포맷: 이미지 + JSON 라벨 (COCO 형식 → YOLO 형식 변환 필요)
- 권장 클래스별 최소 수량: **500장 이상**

### 1-2. VOD 프레임 직접 추출 (도메인 갭 방지 필수)

> ⚠️ AI Hub 데이터는 정지 이미지 위주.
> 실제 예능 VOD는 움직임 블러·클로즈업 편집·자막 오버레이가 많아
> AI Hub 데이터만으로 학습 시 도메인 갭 발생 → 실제 추론 성능 저하.
> **`trailers_아름` VOD 프레임을 반드시 학습 데이터에 포함할 것.**

```python
# 기존 frame_extractor.py 활용하여 프레임 추출
from src.frame_extractor import extract_frames

frames, timestamps = extract_frames(
    video_path="VOD_Embedding/data/trailers_아름/xxx.mp4",
    fps=1.0
)
# 추출된 frames를 data/finetune_dataset/train/images/ 에 저장 후 직접 라벨링
```

### 1-3. 우선순위 클래스 (Phase 1 탐지 0건 항목 우선)

| 클래스 | Phase 1 현황 | 파인튜닝 기대 효과 |
|--------|------------|----------------|
| 비빔밥 | 0건 | 직접 bbox 탐지 |
| 김치찌개 / 된장찌개 | 0건 | 직접 bbox 탐지 |
| 굴비 / 생선구이 | 0건 | STT 의존도 감소 |
| 대게 / 새우 | 0건 | 지방특산물 정밀도 향상 |
| 한우 / 삼겹살 | 0건 | 고기구이 카테고리 직접 탐지 |
| 전복 / 장어 | 0건 | 지방특산물 정밀도 향상 |

---

## Step 2 — 라벨링

### 권장 도구

| 도구 | 특징 | 용도 |
|------|------|------|
| **Roboflow** | 웹 기반 협업, YOLOv11 형식 바로 내보내기 | AI Hub 데이터 변환 + 팀 협업 |
| **CVAT** | VOD 파일 직접 업로드 → 프레임별 라벨링 | trailers_아름 VOD 프레임 라벨링 |

### 라벨 형식 (YOLOv11 표준)

```
# {class_id} {x_center} {y_center} {width} {height}  (0~1 정규화)
0 0.5 0.5 0.2 0.3
```

### 데이터셋 폴더 구조

```
Object_Detection/data/finetune_dataset/
├── train/
│   ├── images/     ← AI Hub 이미지 + trailers_아름 프레임 혼합
│   └── labels/     ← YOLO 형식 .txt
├── val/
│   ├── images/
│   └── labels/
└── data.yaml
```

### `data.yaml` 예시

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

## Step 3 — Google Colab Pro 학습

### 3-1. 코랩 요금제 선택

| 요금제 | GPU | 연속 실행 | 권장 여부 |
|--------|-----|---------|---------|
| Free | T4 (불안정) | ~1~2시간 | ❌ 학습 중 끊길 위험 |
| **Pro** | T4 / A100 | ~12시간 | ✅ epochs=100 충분 |
| Pro+ | A100 (우선배정) | ~24시간 | epochs 많이 필요 시 |

> A100 기준 epochs=100 → 약 30분~1시간 완료 예상.

### 3-2. 코랩 학습 코드

```python
# [1] 패키지 설치
!pip install ultralytics

# [2] Google Drive 마운트
from google.colab import drive
drive.mount('/content/drive')

# [3] 데이터셋 확인
# Drive 경로: /content/drive/MyDrive/finetune_dataset/

# [4] 파인튜닝 학습
from ultralytics import YOLO

model = YOLO("yolo11s.pt")   # 기존 yolo11s.pt에서 전이학습

model.train(
    data="/content/drive/MyDrive/finetune_dataset/data.yaml",
    epochs=100,
    imgsz=640,
    device=0,          # 코랩 GPU 자동 할당
    batch=16,
    patience=20,       # Early stopping
    project="/content/drive/MyDrive/runs",
    name="korean_food_v1"
)

# [5] 검증
metrics = model.val()
print(f"mAP@0.5: {metrics.box.map50:.3f}")

# [6] best.pt 위치 확인
# /content/drive/MyDrive/runs/korean_food_v1/weights/best.pt
```

### 3-3. best.pt 저장 위치

학습 완료 후 Drive에서 다운로드:

```
Drive: /runs/korean_food_v1/weights/best.pt
  ↓ 다운로드
로컬: Object_Detection/models/korean_food_v1_best.pt
```

---

## Step 4 — 로컬 파이프라인 통합

### 4-1. 모델 파일 저장

```
Object_Detection/
└── models/
    └── korean_food_v1_best.pt    ← Drive에서 다운로드한 파일
```

> ⚠️ `models/*.pt`는 `.gitignore` 대상 — 커밋 금지.
> 팀원 공유 시 Google Drive 링크 또는 직접 전달.

### 4-2. config 수정 (코드 변경 없음)

`config/detection_config.yaml` 한 줄만 교체:

```yaml
# 기존
model: yolo11s.pt

# Phase 5 교체
model: models/korean_food_v1_best.pt
```

`src/detector.py`, `scripts/batch_detect.py` **코드 수정 불필요**.

### 4-3. CLIP + STT 파이프라인 영향 없음

| 파이프라인 | Phase 5 영향 |
|----------|------------|
| `src/detector.py` | 모델 경로만 변경, 로직 유지 |
| `src/clip_scorer.py` | 변경 없음 |
| `src/context_filter.py` | 변경 없음 — YOLO 라벨 다양성 증가로 식기류 체크 정확도 향상 |
| `src/audio_extractor.py` | 변경 없음 |
| `src/stt_scorer.py` | 변경 없음 |
| `src/keyword_mapper.py` | 변경 없음 |

---

## Step 5 — 검증

### 5-1. 기존 테스트 통과 확인

```bash
cd Object_Detection
python -m pytest tests/test_phase1_setup.py -v
# → 13/13 PASS 유지 필수
```

### 5-2. A/B 비교 (동일 10 VOD 기준)

```python
import pandas as pd

# A: 기존 yolo11s.pt 결과
df_base = pd.read_parquet("data/vod_detected_object_base.parquet")

# B: 파인튜닝 best.pt 결과
df_ft = pd.read_parquet("data/vod_detected_object_ft.parquet")

# 비교 지표
print("=== 한식 라벨 탐지 건수 ===")
korean_labels = ["비빔밥", "김치찌개", "된장찌개", "굴비", "대게", "한우", "삼겹살"]
print("기존:", df_base[df_base.label.isin(korean_labels)].shape[0])
print("파인튜닝:", df_ft[df_ft.label.isin(korean_labels)].shape[0])
```

### 5-3. 검증 기준

| 항목 | 기준 |
|------|------|
| mAP@0.5 | ≥ 0.6 목표 |
| 한식 라벨 탐지 건수 | 기존 0건 → 1건 이상 |
| 기존 테스트 | 13/13 PASS 유지 |
| CLIP context_valid=True 비율 | 기존 대비 유지 또는 향상 |
| STT 키워드 보완 필요성 | 시각 탐지 커버 증가 → STT 의존도 감소 확인 |

---

## 완료 기준

### 데이터 준비
- [ ] AI Hub 음식 데이터 다운로드 (클래스별 500장 이상)
- [ ] trailers_아름 VOD 프레임 추출 및 혼합
- [ ] 라벨링 완료 (Roboflow 또는 CVAT)
- [ ] `data/finetune_dataset/data.yaml` 작성

### 학습
- [ ] Google Colab Pro 환경 설정 (Drive 마운트)
- [ ] `model.train()` 완료 (mAP@0.5 ≥ 0.6)
- [ ] `best.pt` 다운로드 → `models/korean_food_v1_best.pt` 저장

### 통합
- [ ] `config/detection_config.yaml` 모델 경로 교체
- [ ] `tests/test_phase1_setup.py` 13/13 PASS 유지
- [ ] A/B 비교 결과 확인 (한식 탐지 건수 향상)

### 문서
- [ ] `docs/reports/phase5_ab_report.md` 작성 (A/B 비교 수치 포함)

---

## 기대 효과

| 항목 | Phase 4 현재 | Phase 5 이후 |
|------|------------|------------|
| 한식 탐지 | CLIP 우회 (프레임 전체) | YOLO bbox 직접 탐지 |
| 굴비·대게 구분 | STT 의존 (recall 낮음) | 시각 탐지 + STT 이중 확인 |
| context_filter 정확도 | CLIP negative 차단 위주 | YOLO 한식 bbox + 식기류 동반 확인 강화 |
| Shopping_Ad 연동 | concept 기반 매칭 | bbox 좌표 기반 정밀 매핑 가능 |

---

## 알려진 위험 요소

| 위험 | 대응 |
|------|------|
| 도메인 갭 (AI Hub 정지 이미지 vs VOD 동영상 프레임) | trailers_아름 프레임 학습 데이터 혼합 필수 |
| 라벨링 공수 과다 | Roboflow 팀 협업 기능 활용 |
| 코랩 세션 끊김 | Drive 저장 주기적 체크포인트, Pro 요금제 사용 |
| best.pt 용량 (수십 MB) | .gitignore 등록 확인, Drive 공유 |
| **AI Hub aihubshell 해외 IP 차단** | **로컬 INNORIX 다운로드 후 Drive 수동 업로드** |

---

## 📌 구현 접근 방식 비교 (2026-03-16 업데이트)

> 조장(황대원) Ollama 제안 반영. 4가지 접근 방식을 비교하여 현실적 구현 우선순위를 재정의한다.

### 배경

조장 제안: *"OpenAPI/Gemini API는 과금이 비싸니 Ollama 로컬 설치해서 YOLO 보조로 활용하면 어떨까?"*

### 방식 비교

| 항목 | A. 현재 CLIP | B. Ollama→쿼리 생성 | C. Ollama→직접 분석 | D. YOLO 파인튜닝 |
|------|------------|-------------------|-------------------|----------------|
| 속도 | ⚡ 빠름 | ⚡ 빠름 (동일) | 🐢 느림 | ⚡ 빠름 |
| 구현 난이도 | ✅ 완료 | 쉬움 (yaml만 교체) | 중간 | 높음 |
| 한식 커버리지 | 낮음 (수십 개) | **높음 (800종+)** | 높음 | **높음 (직접 탐지)** |
| 런타임 비용 | 무료 | 무료 | GPU/CPU 부하 | 무료 |
| 코드 변경 | 없음 | yaml만 교체 | src 수정 필요 | config 경로만 교체 |
| bbox 좌표 | ❌ 없음 | ❌ 없음 | ❌ 없음 | ✅ 정밀 bbox |
| 학습 데이터 | 불필요 | 불필요 | 불필요 | 840GB + 라벨링 |
| 학습 시간 | 없음 | 없음 | 없음 | ~2시간 (A100) |

### 방식별 파이프라인

**방식 B — Ollama로 CLIP 쿼리 자동 생성 (권장 1순위)**

```
Ollama (사전 1회 실행):
  "한식 800종 CLIP 쿼리를 yaml 형식으로 생성해줘"
  → clip_queries.yaml 자동 생성 (800종 × 다양한 표현)

런타임 파이프라인 (기존과 동일):
  프레임 → YOLO → CLIP(확장된 yaml) → STT → Shopping_Ad
```

**방식 C — Ollama 직접 프레임 분석**

```
프레임 이미지
  → Ollama LLaVA (멀티모달): "이 이미지에 뭐가 보여?"
  → "비빔밥과 된장찌개가 보입니다"
  → 광고 카테고리 추출
```

> ⚠️ 프레임마다 LLM 호출 → 처리 속도 저하. VOD 배치 처리에 부적합.

**방식 D — YOLO 파인튜닝 (본 PLAN 원안)**

```
AI Hub 840GB 학습 → best.pt → config 경로 교체
  → 한식 800종 bbox 직접 탐지
```

### 구현 우선순위 재정의

```
1순위 (즉시): B — Ollama로 clip_queries.yaml 800종 확장
              → 코드 변경 없음, 하루 안에 완성 가능

2순위 (추후): D — YOLO 파인튜닝
              → 이미지 데이터 확보 후 B 위에 추가
              → B + D 조합 시 시너지 최대

보류:         C — Ollama 직접 분석
              → 속도 문제로 VOD 배치 처리 부적합
```

### B + D 조합 효과

```
YOLO(D): 비빔밥 bbox → 정밀 좌표
CLIP(B): 전통시장, 바닷가 등 맥락·장소 탐지
STT:     "영광 굴비" 등 발화 키워드 보완
→ 3중 시그널로 Shopping_Ad 광고 정확도 극대화
```
