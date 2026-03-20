# Phase 5 세션 리포트 — TS 데이터 전처리 시작

- **브랜치**: Object_Detection
- **작성일**: 2026-03-17
- **선행 세션**: 2026-03-16 (Colab 노트북 구현, aihubshell 해외 IP 차단 확인)
- **세션 목표**: TS.z01 로컬 전처리 실행 + Colab 병렬 처리 노트북 구현

---

## 세션 작업 내역

### 1. TS.z01 다운로드 및 압축 해제 완료

- INNORIX로 TS.z01 (100GB) 로컬 다운로드 완료
- 7-Zip으로 압축 해제 → `C:\Users\user\Documents\AI HUB\TS\`
- 해제된 폴더 구조:

```
TS/
├── TS1/
│   └── A/13/A13001/30/
│       ├── 정위/  ← A_13_A13001_가자미구이_30_09.jpg
│       └── 측면/  ← A_13_A13001_가자미구이_30_01.jpg
├── TS10/
└── TS11/
```

- 이미지 파일명 패턴: `{분류}_{코드}_{음식ID}_{음식명}_{각도코드}_{번호}.jpg`

### 2. TL.zip / VL.zip 실제 경로 확인

기본값 경로(`C:\Users\user\Documents\AI HUB\`)와 달리 실제 저장 위치:

| 파일 | 실제 경로 |
|------|----------|
| TL.zip | `C:\Users\user\Downloads\aihub\296.비전영역, 음식이미지 및 정보소개 텍스트 데이터\01-1.정식개방데이터\Training\02.라벨링데이터\TL.zip` |
| VL.zip | `C:\Users\user\Downloads\aihub\296.비전영역, 음식이미지 및 정보소개 텍스트 데이터\01-1.정식개방데이터\Validation\02.라벨링데이터\VL.zip` |

`PLAN_05` 경로표 업데이트 완료.

### 3. prepare_local_dataset.py 실행

경로 인자 명시 후 실행:

```bash
python Object_Detection/scripts/prepare_local_dataset.py \
  --train-labels "C:\Users\user\Downloads\aihub\...\TL.zip" \
  --val-labels   "C:\Users\user\Downloads\aihub\...\VL.zip" \
  --images-dir   "C:\Users\user\Documents\AI HUB\TS"
```

- 예상 소요 시간: 1~2시간 (JSON 23만개 스캔 + 이미지 ~29,000장 변환)
- 출력: `C:\Users\user\Documents\AI HUB\finetune_dataset\` (~4GB)

### 4. Colab 병렬 처리 노트북 신규 생성

**파일**: `notebooks/phase5_ts_drive_preprocess.ipynb`

로컬에서 TS.z01 전처리를 돌리는 동안, Colab A100에서 TS.z02를 병렬 처리하기 위한 독립 노트북.

| Step | 내용 |
|------|------|
| Step 1 | Drive 마운트 + 경로 설정 |
| Step 2 | TS_ZIP_NAME 지정 + Colab 디스크 확인 + 7z 압축 해제 |
| Step 3 | TL.zip / VL.zip 압축 해제 (최초 1회) |
| Step 4 | 640×640 리사이즈 + YOLO 변환 → Drive `finetune_dataset/` 누적 |
| Step 5 | 임시 폴더 정리 + 누적 현황 확인 |

**핵심 설계**:
- `dst_img.exists()` 중복 스킵 — 로컬+Colab 동시 실행 시 충돌 없음 (TS별 이미지 파일명 겹치지 않음)
- `TS_ZIP_NAME` 변수 하나만 바꿔서 TS.z03, z04... 반복 가능
- p7zip-full 설치로 7z/zip 형식 모두 지원

---

## finetune_dataset 누적 구조

```
finetune_dataset/               ← Drive에 이것만 올라감 (~4GB/분할)
├── train/
│   ├── images/
│   │   ├── A_13_A13001_가자미구이_30_01.jpg   ← TS.z01 (640×640)
│   │   ├── B_14_B14001_비빔밥_30_01.jpg       ← TS.z02 추가 시 누적
│   │   └── ...
│   └── labels/
│       ├── A_13_A13001_가자미구이_30_01.txt   ← "42 0.512 0.488 0.234 0.345"
│       └── ...
├── val/
└── data.yaml
```

모든 분할 처리 완료 후 `phase5_finetune_colab.ipynb` Step 4 (`model.train()`) 1회 실행 → `best.pt` 1개 생성.

---

## 파인튜닝 원리 (Transfer Learning)

```
yolo11s.pt (COCO 80종 사전학습 완료)
  ↓ 특징 추출 능력(엣지, 형태, 색상) 재활용
AI Hub 800종 추가 학습
  ↓ epoch마다: 이미지 → 예측 → 정답과 비교 → 가중치 조정
best.pt (한식 800종 직접 bbox 탐지 가능)
```

- 밑바닥부터 학습 시 수백만 장 필요 → 파인튜닝은 수만 장으로 가능
- GPU(A100)가 필요한 건 `model.train()` 단계뿐 — 전처리는 순수 CPU+IO 작업

---

## 현재 상태

| 항목 | 상태 |
|------|------|
| TS.z01 다운로드 | ✅ 완료 |
| TS.z01 7-Zip 해제 | ✅ 완료 |
| prepare_local_dataset.py 실행 | 🔄 진행 중 (~1~2시간) |
| phase5_ts_drive_preprocess.ipynb | ✅ 완료 (커밋 b7b1c30) |
| finetune_dataset Drive 업로드 | 🔲 전처리 완료 후 |
| Colab Step 4 학습 | 🔲 이미지 준비 후 |

---

## 다음 액션

### 즉시
1. `prepare_local_dataset.py` 완료 대기
2. 완료 후: `C:\Users\user\Documents\AI HUB\TS\` 삭제 + `TS.z01` 삭제 (공간 확보)
3. `finetune_dataset\` → Drive 업로드

### 병렬 (TS.z02~)
4. TS.z02 Drive 업로드 → Colab `phase5_ts_drive_preprocess.ipynb` 실행
5. TS.z01 처리 완료 후 TS.z02 로컬 처리도 가능 (`--skip-extract` 플래그)

### 학습 시작 기준
- TS.z01 1개 (~29,000장)만으로 파인튜닝 시작 가능
- 더 많은 데이터 = 더 높은 mAP, 하지만 TS.z01로 먼저 학습 후 best.pt 검증 권장
