# Object_Detection 세션 리포트 — 2026-03-18

## 세션 요약

멀티모달 4종(YOLO+CLIP+STT+OCR) 통합 테스트 실행 및 PR #53 생성.

---

## 주요 작업

### 1. OCR 자막 인식 모듈 추가 (`src/ocr_scorer.py`)

- **목적**: STT 보완 — 출연자가 말 안 해도 자막에 있으면 음식명/장소명 잡음
- **모델**: EasyOCR (한국어+영어), GPU=False
- **기능**:
  - `extract_text(frame)`: 단일 프레임 → 텍스트
  - `extract_texts(frames, timestamps, sample_interval=3)`: N프레임마다 OCR 샘플링
- **제한**: 2글자 이상 키워드만 매칭 (1글자 OCR 오탐 방지)

### 2. 멀티모달 4종 통합 테스트 (`scripts/pilot_multimodal_test.py`)

기존 3종(YOLO+CLIP+STT) → **4종(+OCR)** 확장.

#### 테스트 결과 (VyLh7Sl7dAk.mp4, 먹방 예능)

| 신호 | 건수 | 가중치 | 역할 |
|------|------|--------|------|
| YOLO | 5 | +3 | 음식 존재 타이밍 (COCO 컨텍스트 필터) |
| CLIP | 84 | +1 | 장면 맥락 (지방특산물, 한식) |
| STT | 10 | +3 | 메뉴명 핵심 (소주, 볶음밥, 된장, 참기름) |
| OCR | 35 | +2 | 자막 보완 (흑돼지, 갈비, 여수) |

#### 구간별 트리거

- **21개 구간 중 13개 TRIGGER** (score≥3, 2종 이상 교차검증)
- 최고 점수: score=9, 4종 모두 히트 ([02:10~02:20])
- 단독 신호 구간은 "교차검증 미충족"으로 트리거 차단

### 3. STT 키워드 확충

- `stt_keywords.yaml`: 156→272개
- 한식 31→124개 (국/탕/찌개, 볶음/구이/조림, 반찬, 분식, 재료 추가)
- 캠핑 13개 신규

---

## 알려진 이슈

### OCR 품질 문제 (높은 우선순위)

EasyOCR 한글 인식률이 매우 낮음. 대부분 깨진 텍스트:

```
원문: "노 M이I UI-5 여쉬 해산자 포자 {00000 '닮어구 염각구 이 F"
매칭: "흑돼지", "갈비" → 오탐 가능성 높음
```

**원인**: 예능 자막은 다양한 폰트/색상/크기 + 배경 노이즈가 심해서 EasyOCR 성능 저조

**개선 방안**:
1. PaddleOCR 교체 (한국어 성능 우수)
2. 자막 영역 전처리 (이진화, 노이즈 제거)
3. OCR confidence threshold 추가

### YOLO 도메인 갭

- AI Hub 정물 사진 vs VOD 실제 영상 간 도메인 갭 존재
- mAP@0.5=0.987은 AI Hub 내부 성능, VOD 실전 성능과 무관
- detector_v2의 COCO 사전필터로 오탐 줄였으나 탐지 건수 자체가 적음 (5건)

---

## 커밋 & PR

| 항목 | 내용 |
|------|------|
| 커밋 | `1f84b7c` feat: OCR 자막 인식 모듈 + 멀티모달 4종 통합 |
| PR | [#53](https://github.com/dhwang0803-glitch/dxshcool/pull/53) — Object_Detection → main |
| 보안 점검 | ✅ 통과 (하드코딩/getenv/gitignore 모두 정상) |

---

## 다음 작업 후보

1. **OCR 모델 개선** — PaddleOCR 교체 또는 전처리 강화
2. **배치 파이프라인** — 전체 VOD 트레일러 대상 4종 멀티모달 배치 실행
3. **DB 적재** — `detected_object_yolo/clip/stt` 테이블에 parquet → DB ingest
4. **Shopping_Ad Phase 1** — matcher.py 구현 (STT>CLIP>YOLO 우선순위 매칭)
