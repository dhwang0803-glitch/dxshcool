> ℹ️ best.pt 학습 결과 기록. 파인튜닝 모델이 기본값으로 확정됨 (2026-03-20).
> val mAP 0.99는 AI Hub 분포 유사성 과대평가 — 실전 성능은 test5에서 검증 (COCO 47→2,139건).
> 최신 → `docs/MATCHING_FLOW.md`

# Phase 5 — YOLOv11s 파인튜닝 파일럿 결과 리포트

**작성일**: 2026-03-18
**작성자**: 박아름 (Object_Detection)

---

## 1. 개요

AI Hub '음식 이미지 및 외식 산업 데이터' (TS.z01 분할)로 YOLOv11s 파인튜닝 파일럿을 실행하여, 한식 사물인식 가능 여부를 검증했다.

### 목표
- 기존 COCO 80종 모델에서 한식 탐지 0건 문제 해결
- mAP@0.5 ≥ 0.60 달성 시 합격

---

## 2. 학습 환경

| 항목 | 값 |
|------|-----|
| GPU | NVIDIA A100-SXM4-40GB (Colab Pro) |
| VRAM 사용 | 4.93GB |
| 모델 | YOLOv11s.pt (pretrained, 493/499 weights 전이) |
| Optimizer | MuSGD (lr=0.01, momentum=0.9) |
| epochs | 100 (실제 86에서 세션 끊김) |
| patience | 20 (early stop 미발동) |
| imgsz | 640 |
| batch | 16 |
| AMP | ✅ (Mixed Precision) |
| Augmentation | albumentations (Blur, MedianBlur, ToGray, CLAHE) |

---

## 3. 데이터셋

### 출처
- AI Hub 데이터셋번호 71564: '비전영역, 음식이미지 및 정보소개 텍스트 데이터'
- 분할 파일: TS.z01 (100GB)

### 구성

| 항목 | 값 |
|------|-----|
| train | 20,872장 (20,877 라벨) |
| val | 5,218장 |
| 클래스 | 71개 FC코드 (70개 매핑 확인) |
| 비율 | train 80% / val 20% |
| 이미지 크기 | 640×640 (리사이즈 완료) |

### 대분류 분포 (TS.z01)
- A(특수외식) 42% / B(일반외식·배달) 32% / C(끼니대체) 22% / D(음료) 3%

### data.yaml 이슈
- Drive 업로드 후 data.yaml이 0바이트 → `phase5_pilot_train.ipynb`의 자동 복구 로직으로 해결
- 자동 복구 시 `class_0`, `class_1` 등 임시 이름 부여 (후속 매핑으로 해결)

---

## 4. 학습 결과

### 최종 메트릭 (epoch 86)

| 지표 | 값 | 목표 |
|------|-----|------|
| **mAP@0.5** | **0.990** | ≥ 0.60 |
| mAP@0.5:95 | 0.989 | - |
| Precision | 0.982 | - |
| Recall | 0.983 | - |
| box_loss | 0.1951 | - |
| cls_loss | 0.2060 | - |

### 학습 곡선 요약

| epoch | mAP@0.5 | mAP@0.5:95 | cls_loss |
|-------|---------|-----------|----------|
| 1 | - | - | 2.694 |
| 39 | 0.985 | 0.984 | 0.423 |
| 50 | 0.986 | 0.985 | 0.348 |
| 59 | 0.988 | 0.987 | 0.311 |
| 77 | 0.989 | 0.988 | 0.234 |
| 86 | 0.989 | 0.988 | 0.206 |

- loss 지속 감소, mAP 수렴 중
- epoch 86에서 Colab 세션 타임아웃으로 중단 (early stop 아님)
- `save_period=10`으로 10 epoch마다 체크포인트 저장 + best.pt 매 epoch 갱신

### ⚠️ 높은 mAP 주의

val mAP 0.99는 **AI Hub 데이터 특성** 때문:
- 같은 촬영 세트에서 각도/조명만 변경하여 여러 장 촬영
- 랜덤 80:20 분할 시 거의 동일한 이미지가 train/val에 분산
- **실제 VOD 트레일러 성능은 도메인 갭으로 인해 상당히 낮을 것으로 예상 (0.4~0.7)**

---

## 5. A/B 비교 (Step 5)

### 결과
```
기존 yolo11s.pt:       sandwich(18), pizza(3), dining table(1), cake(1)
파인튜닝 best.pt:      class_1(10), class_44(7), class_4(3)
한식 핵심 클래스 탐지:  기존 0건 → 파인튜닝 0건
```

### 원인 분석
- 파인튜닝 모델은 **실제로 음식을 탐지하고 있음** (class_1=10건, class_44=7건)
- class_1 = 샌드위치/토스트 (41종), class_44 = 버거 (5종)
- **한식 핵심 클래스 0건은 이름 불일치** — KEY_CLASSES가 '굴비', '비빔밥' 등 한국어명으로 비교하는데, 모델 출력은 'class_1', 'class_44'

### 해결
- `config/food_class_names.yaml` 생성: 71개 클래스 ID → 한국어 카테고리 대표명
- `src/detector.py` 수정: 모델 로드 시 자동으로 `model.names` 오버라이드
- **재학습 불필요** — 모델 내부는 숫자로만 탐지, names는 출력 번역용

---

## 6. 클래스 매핑

### AI Hub 데이터 구조
```
대분류(4개) → 중분류(14개) → FC코드(71개) → 메뉴명(800종)

예: A(특수외식) → 향토음식 → FC03S02 → 가자미구이, 갈치구이, 굴비구이 등 11종
```

### 파일명 → FC코드 매핑 방법
```
파일명: A_13_A13001_가자미구이_17_01.jpg
        대분류_중분류_Keycode_음식명_표본번호_촬영각도

라벨:   31 0.503077 0.442724 0.822509 0.401415
        class_id  cx  cy  w  h

→ 파일명의 음식명 + 라벨의 class_id 매칭으로 매핑 추출
```

### 주요 클래스 (광고 매칭 관점)

| ID | 라벨명 | 포함 음식 수 | 광고 연결 |
|----|--------|------------|----------|
| 3 | 치킨 | 38종 | 치킨 프랜차이즈, 배달앱 |
| 4 | 피자 | 27종 | 피자 프랜차이즈 |
| 10 | 볶음류 | 18종 | 밀키트, 양념 |
| 23 | 떡볶이 | 11종 | 분식 프랜차이즈 |
| 27 | 회/생선회 | 10종 | 수산물 직송 |
| 31 | 생선구이 | 11종 | 영광 굴비 등 특산물 |
| 43 | 비빔밥 | 5종 | 한식 밀키트 |
| 44 | 버거 | 5종 | 버거 프랜차이즈 |
| 30 | 커피 | 32종 | 카페 프랜차이즈 |

---

## 7. 산출물

| 파일 | 위치 | 설명 |
|------|------|------|
| best.pt | Drive `runs/korean_food_v1/weights/best.pt` | 파인튜닝 모델 (다운로드 대기) |
| food_class_names.yaml | `config/food_class_names.yaml` | 71개 클래스 한국어 매핑 |
| detector.py | `src/detector.py` | names 자동 오버라이드 로직 추가 |
| phase5_pilot_train.ipynb | `notebooks/phase5_pilot_train.ipynb` | Colab 파일럿 학습 노트북 |
| data.yaml | Drive `finetune_dataset/data.yaml` | 자동 복구 버전 (FC코드 names) |

---

## 8. 다음 단계

### 즉시 (best.pt 다운로드 후)
1. `Object_Detection/models/korean_food_v1_best.pt` 로컬 저장
2. 실제 VOD 트레일러로 A/B 테스트 → 도메인 갭 측정
3. `config/detection_config.yaml`의 model 경로 교체

### 도메인 갭 큰 경우
4. VOD 트레일러 프레임 + AI Hub 이미지 혼합 학습 (PLAN_05 원안)
5. TS.z02~z07 추가하여 클래스당 데이터 증강

### Shopping_Ad 연동
6. YOLO 한국어 라벨 → 텍스트 임베딩 → product_catalog 매칭
7. 예: "생선구이" 임베딩 ↔ "영광 굴비 선물세트" 임베딩 → cosine similarity

---

## 9. 결론

- **학습 자체는 성공** — mAP@0.5 = 0.990으로 목표(0.60) 대폭 초과
- **val 성능은 과대평가** — AI Hub 데이터 분포 유사성 때문, 실전 성능은 별도 검증 필요
- **클래스 이름 문제 해결** — food_class_names.yaml + detector.py 오버라이드로 재학습 없이 해결
- **3채널 시너지 기대** — YOLO가 한식 카테고리를 직접 탐지하면 CLIP context_filter의 식기류 교차검증이 의미를 가짐
