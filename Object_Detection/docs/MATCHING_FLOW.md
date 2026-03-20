# Object_Detection 파이프라인 & 매칭 플로우

> 2026-03-20 기준. best.pt 파인튜닝 모델 기본값 확정.
> 이전 `object_detection_pipeline_flow.md`(3/18)를 통합·대체.

---

## 0. 목적 — 왜 이걸 하는가

IPTV/케이블 VOD 예능을 시청하는 중에, **화면에 나오는 음식이나 관광지에 맞는 광고를 팝업으로 띄운다.**

| 장면 | 탐지 | 광고 액션 |
|------|------|-----------|
| 출연자가 **콩나물국밥**을 먹음 | YOLO+STT "콩나물국밥" | "전주 콩나물국밥 — 제철장터" 채널 이동/시청예약 |
| 출연자가 "이 **한우** 진짜 좋다" | STT "한우" | "횡성 한우 — 제철장터" 채널 이동/시청예약 |
| **순천만** 풍경 B-roll (대사 없음) | CLIP "관광지" + OCR "순천" | "순천만 관광 축제 안내" 지자체 광고 팝업 |

### 광고 2종 (2026-03-19 전략 확정)

| 카테고리 | 트리거 | 광고 액션 |
|---------|--------|-----------|
| **음식** | 음식 장면/발화 탐지 | 제철장터 채널 상품 연계 (채널 이동/시청예약) |
| **관광지/지역** | 관광지 장면/지역명 탐지 | 지자체 광고 팝업 (관광·축제) |

> 대상 VOD: `genre_detail IN ('여행', '음식_먹방')` — 2,958건

### 동작 흐름

```
[1회 사전 배치 처리]
VOD 트레일러 → 4종 멀티모달 분석 → VOD별 ad_category + region 태깅 → DB 적재

[실시간 서빙]
시청자 VOD 재생
  → API_Server: 해당 VOD의 ad_category/region 조회
  → 음식 → "제철장터에서 OO 판매중" 팝업 (채널 이동/시청예약)
  → 관광지 → "OO 지역 축제 안내" 팝업 (지자체 광고)
```

### 구체적 시나리오

**시나리오 1: 먹방 예능 (수요미식회 감자탕)**
```
YOLO: food_detected (감자탕 장면)     → +3
STT:  "감자탕" 발화                   → +3
CLIP: "음식" 장면                     → +2
OCR:  자막에 "감자탕"                 → +2
→ score=10 [4종] 🔥 TRIGGER
→ ad_category=음식 → "감자탕 밀키트 — 제철장터"
```

**시나리오 2: 여행 예능 (순천 여행)**
```
YOLO: 음식 없음 (풍경)               → 0
STT:  "순천" 발화                     → +3
CLIP: "관광지" 장면                   → +2
OCR:  자막에 "순천"                   → +2
→ score=7 [3종] 🔥 TRIGGER
→ ad_category=관광지, region=순천 → "순천만 관광 안내" 지자체 광고
```

**시나리오 3: 풍경 B-roll (대사 없음, BGM만)**
```
YOLO: 0                              → 0
STT:  매칭 없음                       → 0
CLIP: "관광지" 장면                   → +2
OCR:  없음                           → 0
→ score=2 [1종] → 🏔️ TRIGGER (관광지 B-roll 예외)
→ CLIP 단독으로도 관광지 태깅 가능
```

---

## 전체 구조 (1장 요약)

```
영상 파일 (MP4)
    │
    ├──→ [프레임 추출] 1fps 샘플링
    │         │
    │         ├──→ [YOLO v2]  2단계 음식 탐지        → +3점
    │         │     1단계: COCO (yolo11s.pt) → 식기/식탁 컨텍스트 확인
    │         │     2단계: best.pt (한식 71종) → 음식 탐지 (컨텍스트 있을 때만)
    │         │
    │         ├──→ [CLIP]     장면 의미 분류         → +2점
    │         │     ↓ (배치 파이프라인 시)
    │         │     [context_filter] YOLO+CLIP 교차검증 → context_valid 판정
    │         │
    │         └──→ [OCR]      자막 텍스트 추출       → +2점
    │                              │
    │                              └──→ keyword_mapper (stt_keywords.yaml, 599개)
    │
    └──→ [오디오 추출] ffmpeg 16kHz WAV
              │
              └──→ [STT]      음성→텍스트           → +3점
                                   │
                                   └──→ keyword_mapper (stt_keywords.yaml, 599개)

    ──→ [멀티시그널 스코어링] 10초 구간 단위
              │
              ├── score ≥ 3 AND 2종 이상 → 🔥 TRIGGER
              ├── 관광지 CLIP 단독 ≥ 2   → 🏔️ TRIGGER (B-roll)
              └── score ≥ 3 AND 1종      → ⚠️ 단독 (미충족)
```

---

## 1단계: 입력 및 프레임/오디오 추출

### 프레임 추출 (`src/frame_extractor.py`)
```
영상 → cv2.VideoCapture → 1fps 간격 프레임 추출
     → frames: list[ndarray(BGR)]
     → timestamps: list[float(초)]
     → 예: 27분 영상 → ~1,620 프레임
```

### 오디오 추출 (`src/audio_extractor.py`)
```
영상 → ffmpeg -ar 16000 -ac 1 → 16kHz mono WAV (임시파일)
     → STT 완료 후 삭제
```

---

## 2단계: 4종 신호 분석

### 신호 A — YOLO v2 (`src/detector_v2.py`)

**역할**: 화면에 음식이 시각적으로 보이는지 확인

**2단계 구조 (서로 다른 모델 사용):**

```
프레임
  │
  ├─[1단계] COCO 모델 (yolo11s.pt, conf=0.3)
  │    → 일반 물체 탐지 (80종)
  │    → FOOD_CONTEXT_CLASSES 체크:
  │        bowl, cup, fork, knife, spoon, wine glass, bottle,
  │        banana, apple, sandwich, orange, broccoli, carrot,
  │        hot dog, pizza, donut, cake, dining table, oven, microwave
  │    → has_food_context = True/False
  │    → "식기/식탁이 보이는가?" 판정
  │
  └─[2단계] 파인튜닝 모델 (best.pt, conf=0.5)
       → AI Hub 한식 71카테고리 학습 (mAP@0.5=0.987)
       → 감자탕, 비빔밥, 삼겹살 등 한식 시각 탐지
       → food_context=True일 때만 결과 채택
       → label = "food_detected" (카테고리명은 STT/OCR이 담당)
       → food_context=False → 전부 탈락 (오탐 차단)
```

**왜 2단계인가:**
- best.pt 단독 사용 시 사람 얼굴을 "해천탕"으로 잡는 등 오탐 발생
- COCO 1단계가 "식기가 있는 장면"만 통과시켜서 오탐 차단
- COCO 단독(47건) vs best.pt+COCO필터(2,139건) — 한식 탐지 45배 향상

**best.pt 없을 때:** COCO fallback (yolo11s.pt) — 서양 음식만 탐지 가능

**출력**: `[{vod_id, frame_ts, label="food_detected", confidence, bbox}]`
**가중치**: +3점

### 신호 B — CLIP (`src/clip_scorer.py`)

**역할**: 장면 전체의 의미 분류 (음식 장면 / 관광지 장면)

> **best.pt 도입 후 역할 변화**: 음식 장면은 YOLO가 거의 다 잡으므로,
> CLIP의 핵심 기여는 **관광지 장면 탐지**와 **YOLO 못 잡는 음식 보완**으로 집중됨.

```
프레임
  │
  └─ clip-ViT-B-32-multilingual-v1
       ├─ 이미지 인코더: clip-ViT-B-32 (영어)
       └─ 텍스트 인코더: multilingual (한국어 지원)

  clip_queries_ko.yaml (115개 쿼리):
  ┌──────────┬────────────────────────────────────────┐
  │ 카테고리  │ 쿼리 예시                               │
  ├──────────┼────────────────────────────────────────┤
  │ 음식     │ "한식 밥상 식탁", "삼겹살 불판 연기"     │
  │ (59개)   │ → best.pt와 겹치지만 YOLO 미탐 보완     │
  ├──────────┼────────────────────────────────────────┤
  │ 관광지   │ "해변 일출 풍경", "한국 산 등산로"       │
  │ (30+개)  │ → YOLO가 못 잡는 영역, CLIP 핵심 역할   │
  ├──────────┼────────────────────────────────────────┤
  │ negative │ "사람 얼굴 클로즈업", "만화", "재난"     │
  │ (20+개)  │ → 오탐 차단                             │
  └──────────┴────────────────────────────────────────┘

  매칭 로직:
    1. 각 프레임 × 115개 쿼리 → 코사인 유사도
    2. score ≥ 0.30 → 매칭
    3. negative 최고 ≥ positive 최고 → 프레임 전체 억제
```

**출력**: `[{vod_id, frame_ts, concept, clip_score, ad_category="음식"|"관광지"}]`
**가중치**: +2점

### 신호 C — STT (`src/stt_scorer.py` + `src/keyword_mapper.py`)

**역할**: 음성에서 음식명/지역명 추출 (가장 정확한 구체적 신호)

```
WAV 오디오
  └─ openai-whisper (small, 한국어)
       → segments: [{start, end, text}, ...]

  각 segment.text → keyword_mapper.match()
```

**10초 구간 배정**: `start_ts < 구간끝 AND end_ts > 구간시작` → 해당 구간에 포함
(경계에 걸리면 양쪽 구간 모두 포함 가능)

**가중치**: +3점

### 신호 D — OCR (`src/ocr_scorer.py` + `src/keyword_mapper.py`)

**역할**: 자막에서 음식명/지역명 추출 (STT 보완)

```
프레임 (3프레임마다 = 3초 간격 샘플링)
  └─ EasyOCR (한국어+영어, CPU)
       → text: "골목식당 콩나물국밥집 SBS"

  각 OCR text → keyword_mapper.match()
       → 2글자 이상만 채택 (1글자 오탐 방지)
```

**중복 텍스트 처리**: 동일 자막이 연속 프레임에서 반복 추출될 수 있음.
10초 구간 스코어링에서는 해당 구간 내 OCR 매칭 "있음/없음"으로만 +2점 부여
(건수가 아니라 존재 여부만 판정).

**가중치**: +2점

---

## 3단계: keyword_mapper 매칭 상세 (`src/keyword_mapper.py`)

> STT와 OCR이 **동일한** keyword_mapper를 사용

### yaml 구조 (`config/stt_keywords.yaml`, 599개)

```yaml
음식:              # ad_category = "음식"
  전주콩나물국밥:  # 키워드 (가장 긴 것 우선 매칭)
    ad_hints: ["전주 콩나물국밥 — 제철장터"]

관광지:            # ad_category = "관광지"
  전주:
    ad_hints: ["전주 한옥마을 관광"]
```

### 키워드 3단 계층 (599개)

```
┌─ 음식 (약 400개) ─────────────────────────────────────────────┐
│                                                                │
│  1순위: 지역+음식 조합 (최우선, 가장 김)                        │
│    전주콩나물국밥, 부산돼지국밥, 춘천닭갈비, 강릉초당순두부      │
│    통영충무김밥, 여수간장게장, 횡성한우, 영덕대게 ...            │
│                                                                │
│  2순위: 음식 복합어 (중간 길이)                                 │
│    콩나물국밥, 돼지국밥, 차돌된장찌개, 오징어볶음밥              │
│    해물칼국수, 대패삼겹살, 양념치킨, 로제떡볶이 ...              │
│                                                                │
│  3순위: 단일 음식명 (기본 백오프)                               │
│    콩나물, 국밥, 삼겹살, 오징어, 김치, 된장, 떡볶이 ...         │
│                                                                │
└────────────────────────────────────────────────────────────────┘

┌─ 관광지 (약 200개) ───────────────────────────────────────────┐
│                                                                │
│  명소 고유명사 (가장 김)                                        │
│    전주한옥마을, 동궁과월지, 북촌한옥마을, 대천해수욕장 ...      │
│                                                                │
│  도시/지역명                                                    │
│    전주, 부산, 제주, 강릉, 속초, 순천, 남해 ...                 │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

### 매칭 알고리즘

```
[초기화 — yaml 로드 시 1회]

1. 각 키워드 → 한국어 경계 정규식 생성
   "콩나물" → (?<![가-힣])콩나물(?=[을를이가은는의에로와과도서까지만]|[^가-힣]|$)
   앞: 한글 바로 앞이면 거부 ("잔콩나물" X)
   뒤: 조사 허용, 한글 이어지면 거부 ("콩나물이" O, "콩나물국밥"에서 단독 매칭 O)

2. 포함관계 테이블 (긴 키워드 우선 정렬)
   전주콩나물국밥 > 콩나물국밥 > 콩나물, 국밥
```

```
[매칭 — 매 텍스트마다]

"전주콩나물국밥 맛있다" 입력 시:

Step 1: 전체 정규식 스캔
  → matched = {전주콩나물국밥, 콩나물국밥, 콩나물, 국밥, 전주}

Step 2: 포함관계 제거 (긴 것에 포함된 짧은 것 제거)
  → 콩나물 ⊂ 콩나물국밥 ⊂ 전주콩나물국밥 → 제거
  → 국밥 ⊂ 콩나물국밥 → 제거
  → 전주 ⊂ 전주콩나물국밥 → 제거

Step 3: 최종
  → "전주콩나물국밥" 1건만 (ad_category=음식) ✅
```

---

## 4단계: 멀티시그널 스코어링

### 10초 구간 윈도우

```
영상 전체를 10초 단위로 분할

각 구간:
  YOLO 탐지 있음?  → +3점  (있음/없음, 건수 무관)
  STT 키워드 있음? → +3점  (있음/없음)
  CLIP 매칭 있음?  → +2점  (있음/없음)
  OCR 키워드 있음? → +2점  (있음/없음)

  만점: 10점 (4종 전부)
```

### 가중치 근거

| 신호 | 가중치 | 근거 |
|------|--------|------|
| YOLO | +3 | best.pt로 한식 시각 탐지 정확도 높음 |
| STT | +3 | "콩나물국밥" 정확히 발화 → 가장 구체적 |
| OCR | +2 | 자막 텍스트 → STT 보완 (중복 가능) |
| CLIP | +2 | 장면 분위기 → 관광지 핵심, 음식은 YOLO 보완 |

### TRIGGER 판정

```
IF score ≥ 3 AND signal_types ≥ 2:
    → 🔥 TRIGGER

ELIF CLIP 관광지 AND score ≥ 2 AND signal_types == 1:
    → 🏔️ TRIGGER (관광지 B-roll 예외)
    → BGM만 있는 풍경 구간용

ELIF score ≥ 3 AND signal_types == 1:
    → ⚠️ 단독 (교차검증 미충족)

ELSE:
    → (약함)
```

---

## 음식 vs 여행 — 신호별 역할 차이

> **걱정 포인트**: best.pt는 음식 탐지 전용 → 여행 영상에서 YOLO가 무력화되지 않나?

### 음식 먹방 영상

```
YOLO: ★★★ 핵심. best.pt가 한식 거의 다 잡음 (2,139건/15분)
STT:  ★★★ "감자탕", "콩나물국밥" 등 구체적 음식명
CLIP: ★★  YOLO와 겹치지만 보완
OCR:  ★★  자막에 음식명 있을 때 보완
→ 4종 모두 활성, 교차검증 쉬움
```

### 여행 풍경 영상

```
YOLO: ☆   음식 없는 풍경 → best.pt 탐지 0건 (정상 동작)
STT:  ★★★ "순천", "제주", "불국사" 등 지역명 추출 핵심
CLIP: ★★★ "관광지" 장면 분류 → B-roll 단독 TRIGGER 가능
OCR:  ★★  자막에 지역명/명소명
→ STT + OCR + CLIP 3종으로 충분. YOLO 없어도 TRIGGER 가능
```

### 여행 먹방 혼합 영상

```
풍경 구간: CLIP 관광지 단독 TRIGGER (🏔️)
식당 구간: YOLO + STT + CLIP + OCR 풀가동 (🔥)
→ 한 VOD에서 ad_category = 음식 + 관광지 멀티라벨 태깅 가능
```

**핵심**: 여행 영상에서 YOLO가 0건이어도 문제 없음.
CLIP 관광지 단독 규칙 + STT/OCR 지역명 매칭이 여행 커버리지를 담당.
test12(순천 여행)에서 YOLO 13건밖에 안 잡혔지만 STT+OCR로 14 TRIGGER 발생.

---

## 5단계: 산출물

### parquet 출력

| 파일 | 신호 | 주요 컬럼 |
|------|------|-----------|
| `vod_detected_object.parquet` | YOLO | vod_id, frame_ts, label, confidence, bbox |
| `vod_clip_concept.parquet` | CLIP | vod_id, frame_ts, concept, clip_score, ad_category |
| `vod_stt_concept.parquet` | STT | vod_id, start_ts, end_ts, transcript, keyword, ad_category, ad_hints |

### VOD 단위 최종 태깅

```
VOD별 TRIGGER 구간의 ad_category 집계:
  → 멀티라벨 가능: ad_category = ["음식", "관광지"]
  → region = STT/OCR에서 가장 빈출한 지역명
  → Shopping_Ad가 소비:
      음식 → 제철장터 상품 매칭
      관광지 → 지자체 광고 소재 매칭
```

---

## context_filter 상세 (`src/context_filter.py`)

> **호출 위치**: `batch_clip_score.py` — CLIP records 생성 후, parquet 저장 전에 호출.
> pilot_multimodal_test.py의 멀티시그널 스코어링에서는 직접 사용하지 않음.

```
CLIP record 1건 (frame_ts, concept, clip_score, ad_category)
    │
    └──→ context_filter.validate(yolo_labels, clip_scores, ad_category)
              │
              ├─[1] Global Brand Safety (전 카테고리)
              │     top 쿼리에 "만화/재난/포스터/스튜디오" → 차단
              │     2위 이하도 score ≥ 0.22이면 → 차단
              │
              ├─[2] 관광지 AND 조건 (ad_category=관광지)
              │     travel_groups 내 서로 다른 2그룹 이상 히트 필요
              │     미충족 → 차단
              │
              ├─[3] 음식 Negative (ad_category=음식)
              │     "금붕어/수조/낚시/장식용" → 차단
              │
              └─[4] 음식 식기류 체크
                    YOLO에 food 라벨 있는데 식기류 없음 → 차단
                    → context_valid: True/False, context_reason: str
```

## location_tagger 상세 (`src/location_tagger.py`)

> **호출 위치**: `batch_clip_score.py` + `batch_stt_score.py` — `--random-location` 플래그 사용 시.

```
현재 상태: 랜덤 시뮬레이션
  → random_location() → 한국 위경도 범위 내 랜덤 좌표 생성
  → get_region(lat, lng) → 13개 시/도 경계 매칭 → "전라남도" 등
  → get_ad_hints(region) → 지역별 광고 힌트 리스트

실서비스 전환 시:
  → random_location() → IPTV STB의 실제 GPS/IP 기반 좌표로 대체
  → 함수 시그니처 동일: tag(lat, lng) → {region, ad_hints}
  → 코드 변경 없이 좌표 소스만 교체

현재 region 신뢰도: 랜덤이므로 0% (시뮬레이션 전용)
실서비스 region 신뢰도: STB 위치 정확도에 의존 (시/도 수준 ~99%)
```

---

## best.pt 학습 조건

| 항목 | 값 |
|------|-----|
| 데이터셋 | AI Hub #71564 '음식이미지 및 정보소개 텍스트 데이터' (TS.z01) |
| 기반 모델 | YOLOv11s (yolo11s.pt) |
| 학습 이미지 | train 20,872장 (20,877 라벨) |
| 클래스 | 71개 FC코드 (대분류4 → 중분류14 → FC71 → 메뉴800종) |
| epochs | 100 설정 / 실제 86에서 Colab 세션 타임아웃 |
| imgsz | 640 |
| batch | 16 |
| patience | 20 (early stop) |
| 학습 환경 | Google Colab A100 |
| **val mAP@0.5** | **0.990** |
| val mAP@0.5:95 | 0.989 |
| 파일 크기 | 57MB |

> ⚠️ **val mAP 0.99는 과대평가**: AI Hub 데이터 분포 유사성 때문.
> 실제 VOD 트레일러 성능은 별도 검증 필요 (test5 기준 음식 장면 탐지 확인됨).
> 추가 학습 시: TS.z02~z07 추가 또는 VOD 프레임 혼합 학습 고려.

상세: `docs/reports/phase5_pilot_result_20260318.md`

---

## 설정 파일 요약

| 파일 | 역할 | 키 수치 |
|------|------|---------|
| `config/detection_config.yaml` | YOLO conf/iou/fps | conf=0.5, fps=1 |
| `config/clip_queries_ko.yaml` | CLIP 쿼리 | 115개 (음식59+관광지30+negative) |
| `config/stt_keywords.yaml` | STT/OCR 키워드 | **599개** (음식400+관광지200) |

## 모델 파일

| 파일 | 용도 | 크기 |
|------|------|------|
| `models/best.pt` | 한식 71종 파인튜닝 (기본값) | 57MB |
| `yolo11s.pt` | COCO 80종 (1단계 필터 + fallback) | 자동 다운로드 |

## 코드 파일 요약

| 파일 | 역할 |
|------|------|
| `src/frame_extractor.py` | MP4 → frames + timestamps |
| `src/audio_extractor.py` | MP4 → 16kHz WAV |
| `src/detector_v2.py` | YOLO 2단계 (COCO필터 + best.pt) |
| `src/clip_scorer.py` | CLIP 장면 분류 |
| `src/stt_scorer.py` | Whisper STT |
| `src/ocr_scorer.py` | EasyOCR 자막 추출 |
| `src/keyword_mapper.py` | 키워드 매칭 (599개, 긴 것 우선) |
| `src/context_filter.py` | Brand Safety + 음식 컨텍스트 필터 (batch_clip_score용) |
| `src/location_tagger.py` | 위경도→지역명 (배치 시 랜덤 시뮬, 실서비스 시 GPS 대체) |
| `src/vod_filter.py` | DB ct_cl 조건 VOD 필터링 |

---

## 검증 필요 사항 (TODO)

### P0 — 파이프라인 신뢰도 (즉시)
- [ ] **test9/10/11 (비음식 영상) best.pt false positive 확인**
      → 음식 없는 영상에서 오탐 많으면 전체 신뢰도 무너짐
- [ ] **test12 (순천 여행) best.pt로 재실행**
      → 여행 영상에서 관광지 TRIGGER 정상 동작 + YOLO 오탐 없는지 확인 (진행 중)

### P1 — 성능 검증 (이번 주)
- [ ] best.pt로 test1~test13 전체 재실행 — COCO 대비 TRIGGER 변화 비교
- [ ] 2,139건 탐지 중 오탐 샘플 체크 (trigger_frames 이미지 눈으로 확인)
- [ ] best.pt 못 잡는 카테고리 파악 → 추가 학습 데이터 선별 근거

### P2 — 엣지케이스 (여유 시)
- [ ] OCR 중복 텍스트가 스코어에 미치는 영향 확인 (이미 있음/없음 판정이라 영향 제한적)
- [ ] CLIP 음식 쿼리 59개 리밸런싱 검토 (best.pt와 겹치므로 관광지 쪽 강화 가능)
