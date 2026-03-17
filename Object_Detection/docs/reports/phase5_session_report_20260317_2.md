# Phase 5 세션 리포트 — TS.z01 전처리 완료 + 아키텍처 설계

- **브랜치**: Object_Detection
- **작성일**: 2026-03-17 (2차 세션)
- **선행 세션**: 2026-03-17 1차 (TS.z01 전처리 시작)
- **PR**: #43 오픈

---

## 세션 작업 내역

### 1. prepare_local_dataset.py 버그 수정 및 전처리 완료

**수정 내역:**

| 버그 | 원인 | 수정 |
|------|------|------|
| 성공 0건 | NTFS 스캔 순서 — D분류 JSON 먼저 스캔 | `process_split` 이미지 매칭 사전 필터 추가 (185,553→26,092) |
| cv2.imread 실패 | Windows 한글 경로 (`정위/`, `측면/`) | `cv2.imdecode(np.fromfile(...))` 로 교체 |
| cv2.imwrite 실패 | 동일 | `cv2.imencode + buf.tofile` 로 교체 |

**최종 결과:**
```
train: 26,090/26,092 성공 (99.99%)
val:   0장 (VS.zip 미다운로드 — 정상)
클래스: 71종
폴더:  2.0 GB
```

---

### 2. split_val.py 신규 추가

train 80:20 분리 스크립트 (`Object_Detection/scripts/split_val.py`).

```
실행 결과:
  train: 20,872장
  val:   5,218장 (20.0%)
```

---

### 3. phase5_ts_drive_preprocess.ipynb Step 4.5 추가

Colab에서 TS 분할 반복 처리 시 누적 train/val 비율을 자동으로 80:20 유지하는 셀 추가.

**로직**: 전체(train+val) 대비 val 부족분만 train에서 이동 → 항상 20% 유지.

---

### 4. TS.z01 데이터 구성 분석

실제 파일명으로 확인한 대분류 분포:

| 대분류 | 의미 | 이미지 수 | 비율 |
|--------|------|---------|------|
| A | 특수외식메뉴 | 8,867장 | 42% |
| B | 일반외식·배달음식 | 6,640장 | 32% |
| C | 끼니대체메뉴 | 4,689장 | 22% |
| D | 음료·차류 | 676장 | 3% |

→ A 위주가 아니라 4개 대분류 전부 포함.

AI Hub JSON에는 YOLO 학습에 사용하지 않은 데이터도 다수 포함:
- `image_info.weight`: 실중량 (g)
- `image_info.s_weight`: 1인분 표준 중량
- `3d_annotation`: 3D Cuboid 꼭짓점 8개
- `nutrition`: 칼로리, 탄수화물, 지질, 단백질, 나트륨 등
- `food_type.loc`: 향토음식 지역 정보

---

### 5. 파인튜닝 방식 및 성능 분석

**학습 방식**: Transfer Learning (전체 가중치 업데이트)
- yolo11s.pt (COCO 80종) → 한식 71종 head 교체 후 전체 레이어 재학습

**A100 기준 예상 학습 시간:**
| 구성 | 시간 |
|------|------|
| TS.z01만 (20,872장) | 30~50분 |
| TS.z01~z03 (~62,000장) | 60~90분 |

**VRAM**: ~5~8GB (A100 40GB의 12~20% 수준, batch=32로 올려도 여유)

**전략**: TS.z03까지만 학습 후 mAP@0.5 ≥ 0.6 확인 → 부족 시 추가 데이터

---

### 6. 파인튜닝 병목 분석

| 단계 | 시간 | 병목 |
|------|------|------|
| INNORIX 다운로드 (100GB) | 1~8시간 | 🔴 최대 병목 |
| 7-Zip 압축 해제 | 30~60분 | 🟡 |
| collect_classes (JSON 18만개) | 15~30분 | 🟡 매번 실행됨 |
| 이미지 변환 26,092장 | 30~60분 | 🟡 |
| Colab A100 학습 | 30~50분 | 🟢 낮음 |

**개선 가능**: collect_classes 결과를 `classes.json`으로 캐싱 → TS.z02부터 30분 절약.

---

### 7. UI/UX 아키텍처 설계

**확정된 구조: 사전 배치 처리 + 영상 분리**

```
[사전 처리 — 1회]
트레일러 5,726개 (로컬)
  → YOLO + CLIP + STT 배치 처리
  → serving.shopping_ad DB 저장 (vod_id, frame_ts, product_id)
  → 트레일러 파일 삭제 가능 ← 영상과 광고 데이터 완전 분리

[서비스 — 실시간]
UI에서 영상 재생 (YouTube iframe / HTML5 video)
  → currentTime 폴링 (0.5~1초)
  → API_Server 쿼리 → DB 조회 → 팝업 표시
```

**YouTube iframe vs 로컬 트레일러:**
- 데모: 로컬 `<video>` 태그 서빙 (CORS 없음, vod_id 매핑 완성)
- 실제 서비스: YouTube iframe + vod_id↔YouTube URL 매핑 테이블

---

### 8. DB 추가 필요 컬럼 (황대원 협의 필요)

**`public.vod` 추가:**

| 컬럼 | 타입 | 용도 |
|------|------|------|
| `youtube_video_id` | VARCHAR(20) | iframe 재생 |
| `duration_sec` | FLOAT | 영상 길이 |
| `trailer_processed` | BOOLEAN | 사전 처리 완료 여부 |

**`serving.shopping_ad` 신규 (스키마 미확정):**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | VARCHAR(64) | 영상 식별자 |
| `ts_start` | FLOAT | 팝업 시작 타임스탬프 |
| `ts_end` | FLOAT | 팝업 종료 타임스탬프 |
| `product_id` | INTEGER | 상품 ID |
| `ad_category` | VARCHAR | 광고 카테고리 |
| `source` | VARCHAR | 탐지 출처 (YOLO/CLIP/STT) |
| `confidence` | FLOAT | 신뢰도 |

**`product_catalog` 신규 (없음):**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `product_id` | SERIAL PK | 상품 ID |
| `product_name` | VARCHAR | 상품명 |
| `category` | VARCHAR | 카테고리 |
| `price` | INTEGER | 가격 |
| `image_url` | VARCHAR | 상품 이미지 |
| `purchase_url` | VARCHAR | 구매 링크 |

---

## 현재 상태

| 항목 | 상태 |
|------|------|
| TS.z01 전처리 | ✅ 완료 (26,090장) |
| train/val 80:20 분리 | ✅ 완료 (20,872 / 5,218) |
| finetune_dataset Drive 업로드 | 🔲 예정 |
| Colab Step 3~4 학습 | 🔲 Drive 업로드 후 |
| collect_classes 캐싱 최적화 | 🔲 선택사항 |

---

## 전체 파이프라인 블로커

| 블로커 | 담당 | 우선순위 |
|--------|------|---------|
| `product_catalog` 없음 | 팀 공통 | 🔴 1순위 |
| `Shopping_Ad matcher.py` 미구현 | Shopping_Ad | 🔴 1순위 |
| `serving.shopping_ad` 스키마 미확정 | 황대원 협의 | 🔴 1순위 |
| `public.vod.youtube_video_id` 없음 | 황대원 협의 | 🟡 2순위 |

---

### 9. 탐지 결과 DB 저장 위치 확정

로컬에서 모델 실행 후 탐지된 사물 리스트 저장 위치: `public.detected_objects`

```sql
public.detected_objects
  vod_id      VARCHAR(64)  -- 영상 식별자
  frame_ts    FLOAT        -- 타임스탬프 (초)
  label       VARCHAR      -- 탐지 사물명
  confidence  FLOAT        -- 신뢰도 (0~1)
  bbox        FLOAT[]      -- [x1, y1, x2, y2]
```

- 현재는 로컬 `vod_detected_object.parquet`에 동일 구조로 저장 중
- DB 스키마 확정 후 `scripts/ingest_to_db.py`로 적재 예정
- Shopping_Ad만 소비하면 parquet으로 충분, UI 분석 필요 시 DB 적재
- **황대원에게 테이블 생성 요청 필요**

---

## 다음 액션

1. `finetune_dataset/` → Drive 업로드
2. Colab `phase5_finetune_colab.ipynb` Step 3~4 실행 → `best.pt` 확보
3. 황대원에게 `serving.shopping_ad` 스키마 + `product_catalog` 협의 요청
4. Shopping_Ad `matcher.py` 구현
