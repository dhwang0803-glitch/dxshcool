# Object_Detection 브랜치 — 전체 구현 플로우

- **작성일**: 2026-03-15
- **작성자**: 박아름
- **브랜치**: Object_Detection
- **테스트 현황**: 51/51 PASS (Phase 1~4 전체)

---

## 1. 프로젝트 목적

IPTV/케이블 VOD 영상에서 **장면·객체·음성**을 인식하여,
그 맥락에 맞는 **광고 트리거**를 생성하는 로컬 파이프라인 구축.

Shopping_Ad 브랜치가 이 파이프라인의 산출물(parquet 3종)을 소비하여
실제 광고를 노출한다.

---

## 2. 전체 데이터 플로우

```
VOD 영상 파일 (.mp4 / .webm)
│
├─── [Phase 1 · YOLO] ──────────────────────────────────────────────────
│    frame_extractor.py → N fps 프레임 샘플링
│    detector.py        → YOLOv8 추론 (COCO 80종, confidence ≥ 0.5)
│    batch_detect.py    → 배치 실행
│    └─→ vod_detected_object.parquet
│         (vod_id, frame_ts, label, confidence, bbox)
│
├─── [Phase 2/3 · CLIP] ─────────────────────────────────────────────────
│    frame_extractor.py      → N fps 프레임 샘플링 (YOLO와 동일 ts)
│    clip_scorer.py          → 듀얼 모델 코사인 유사도 스코어링
│    context_filter.py       → 광고 트리거 적합성 판단 (오탐 차단)
│    location_tagger.py      → 사용자 위치 시뮬레이션 → 지역 태그
│    batch_clip_score.py     → 배치 실행 (YOLO 인덱스 로드 포함)
│    └─→ vod_clip_concept.parquet
│         (vod_id, frame_ts, concept, clip_score, ad_category,
│          context_valid, context_reason, region, ad_hints, sim_lat, sim_lng)
│
└─── [Phase 4 · STT] ────────────────────────────────────────────────────
     audio_extractor.py  → ffmpeg → 16kHz mono WAV
     stt_scorer.py       → Whisper small → transcript + 구간 타임스탬프
     keyword_mapper.py   → 키워드 매칭 → ad_category + ad_hints
     batch_stt_score.py  → 배치 실행
     └─→ vod_stt_concept.parquet
          (vod_id, start_ts, end_ts, transcript, keyword,
           ad_category, ad_hints, region, sim_lat, sim_lng,
           context_valid, context_reason)

                    ↓ 3개 parquet → Shopping_Ad 브랜치
          vod_id + frame_ts(또는 시간 구간) 기준 조인
                    ↓
          context_valid=True 레코드만 광고 매칭 대상
                    ↓
          사용자 실제 위치 + ad_category → 지역 특산물 광고 선택
```

---

## 3. Phase별 상세 구현

---

### Phase 1 — YOLO 객체 탐지

**목적**: VOD 프레임에서 COCO 80종 객체를 탐지하여 label + bbox + confidence 저장.

#### 구현 파일

| 파일 | 역할 |
|------|------|
| `src/frame_extractor.py` | `cv2.VideoCapture`로 N fps 프레임 추출. 타임스탬프 `round(idx/fps, 3)` |
| `src/detector.py` | `ultralytics.YOLO` 래퍼. confidence 필터링, bbox 절대좌표 변환 |
| `scripts/batch_detect.py` | 배치 실행. 상태 파일(`detect_status.json`)로 재시작 지원 |

#### 모델 선택

| 모델 | 속도 | 정확도 | 권장 |
|------|------|--------|------|
| yolo11n.pt | ⚡ 빠름 | 낮음 | 테스트 |
| **yolo11s.pt** | 중간 | 중간 | **CPU 기본값** |
| yolov8x.pt | 느림 | 높음 | GPU |

#### 산출물 스키마

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | 영상 파일명(확장자 제외) |
| `frame_ts` | float | 프레임 타임스탬프 (초, 소수 3자리) |
| `label` | str | YOLO 클래스명 (예: "fish", "apple") |
| `confidence` | float | 신뢰도 0.0~1.0 (필터 기준 0.5) |
| `bbox` | list[float] | [x1, y1, x2, y2] 픽셀 절대좌표 |

#### 테스트: **13/13 PASS**

---

### Phase 2 — CLIP Zero-shot 장면 인식

**목적**: YOLO가 못 잡는 장면/맥락(바닷가, 한식 밥상, 지방 특산물 등)을
텍스트 쿼리와의 코사인 유사도로 보완.

#### CLIP 모델 구조 (Phase 3에서 최적화)

```
이미지 프레임 ──→ clip-ViT-B-32                ──→ 512차원 벡터
한국어 쿼리   ──→ clip-ViT-B-32-multilingual-v1 ──→ 512차원 벡터 (동일 공간)
                                                        ↓
                                                 코사인 유사도
                                                        ↓
                                             threshold 0.26 이상만 태그
```

#### KoCLIP A/B 실험 (동일 VOD 10건 공정 비교)

| 설정 | 총 건수 | concept 수 | std | 판정 |
|------|--------|-----------|-----|------|
| EN (`clip-ViT-B-32`, th=0.25) | 1,385 | 20/43 | 0.013 | 기준 |
| KO (`multilingual`, th=0.25) | 3,871 | 33/43 | 0.012 | 너무 많음 |
| **KO (`multilingual`, th=0.26)** | **1,925** | **23/43** | **0.012** | **최적 채택** |
| KO (`multilingual`, th=0.27) | 889 | 14/43 | — | 너무 적음 |

**채택 근거**: 판별력(std) 동등, 한국 특산물 concept 커버리지 우위(23 vs 20),
한국어 쿼리로 "굴비 먹는 식사 장면", "대게 해산물" 직접 탐지 가능.

#### 쿼리 카테고리 구성 (`config/clip_queries.yaml`)

| 카테고리 | 쿼리 수 | 주요 쿼리 |
|---------|--------|---------|
| 장소 | 9개 | 바닷가, 전통시장, 주방, 수산시장 등 |
| 한식 | 7개 | 한식 밥상, 해산물, 전골, 생선구이 등 |
| 홈쇼핑 | 5개 | 가전제품, 가구, 침구, 여행 패키지 등 |
| 지방특산물 | 7개 | 굴비, 대게, 전복, 한우, 젓갈, 굴, 장어 |
| 과일채소 | 6개 | 파인애플, 망고, 딸기, 수박, 포도 등 |
| 여행지 | 6개 | 유럽, 동남아, 지중해, 일본, 제주도 등 |
| negative | 7개 | 금붕어 수조, 장식용 과일, 낚시, 바닷속, 애니메이션, 재난 등 |

#### 구현 파일

| 파일 | 역할 |
|------|------|
| `src/clip_scorer.py` | 듀얼 모델 초기화, `score_frame()`, `to_records()` |
| `src/location_tagger.py` | 랜덤 위치 시뮬레이션 → 지역명 + ad_hints |
| `scripts/batch_clip_score.py` | 배치 실행, YOLO 인덱스 로드, parquet 저장 |

#### 테스트: **13/13 PASS**

---

### Phase 3 — 광고 연동 인식 확장

**목적**: CLIP 탐지 결과를 실제 광고 트리거로 연결하고,
오탐(금붕어 수조, 장식 과일, 낚시 장면 등)을 차단.

#### Context Filter 설계 (`src/context_filter.py`)

필터는 3단계로 구성된다:

```
1단계 — Global Brand Safety (모든 카테고리 공통)
    ├── top-1 쿼리에 재난/애니메이션 키워드 → 차단
    └── secondary: 해당 키워드 쿼리 점수 ≥ 0.22 → 차단

2단계 — 음식 카테고리 전용 (지방특산물/한식/과일채소)
    ├── top-1 쿼리에 낚시/바닷속/장식 키워드 → 차단
    └── secondary: 해당 키워드 쿼리 점수 ≥ 0.22 → 차단

3단계 — YOLO 식기류 체크 (음식 카테고리)
    └── YOLO에서 음식 탐지 + 식기류(젓가락/그릇 등) 없음 → 차단

비음식 카테고리(홈쇼핑/여행지) → 2·3단계 미적용
```

| context_valid | context_reason | 의미 |
|--------------|---------------|------|
| True | `eating_scene` | 정상 식사 장면 |
| True | `non_food_category` | 홈쇼핑/여행지 |
| True | `keyword_match` | STT 키워드 매칭 |
| False | `brand_safety:...` | 재난/애니 감지 |
| False | `brand_safety_secondary:...` | 재난/애니 2등 감지 |
| False | `context_blocked:...` | 낚시/바닷속 등 감지 |
| False | `food_context_secondary:...` | 낚시/바닷속 2등 감지 |
| False | `no_tableware_with_food` | 식기류 없는 음식 |

#### YOLO+CLIP 통합 (`scripts/batch_clip_score.py`)

```python
# 기존 (문제)
ctx_filter.validate(yolo_labels=set(), ...)  # 식기류 체크 비활성

# 개선
yolo_index = load_yolo_index(Path("data/vod_detected_object.parquet"))
# → {vod_id: {frame_ts: set(labels)}}
yolo_labels = yolo_index.get(vod_id, {}).get(frame_ts_key, set())
ctx_filter.validate(yolo_labels=yolo_labels, ...)  # 실제 라벨 전달
```

#### 성능 개선

| 항목 | 이전 | 개선 |
|------|------|------|
| 프레임 조회 | `timestamps.index()` O(n²) | `ts_to_scores` dict O(1) |
| `--random-location` | `store_true+default=True` (항상 켜짐) | `BooleanOptionalAction` (끄기 가능) |
| negative 키워드 | 영어만 (한국어 쿼리 전환 후 매칭 깨짐) | 한국어+영어 이중 등록 |

#### 산출물 스키마 (`vod_clip_concept.parquet`)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `frame_ts` | float | 프레임 타임스탬프 (초) |
| `concept` | str | 매칭된 한국어 쿼리 텍스트 |
| `clip_score` | float | 코사인 유사도 (threshold 0.26 이상) |
| `ad_category` | str | 광고 카테고리 |
| `context_valid` | bool | 광고 트리거 적합 여부 |
| `context_reason` | str | 판단 근거 |
| `region` | str | 시뮬레이션 지역명 |
| `ad_hints` | str | 지역별 광고 힌트 |
| `sim_lat` | float | 시뮬레이션 위도 |
| `sim_lng` | float | 시뮬레이션 경도 |

#### 테스트: **13/13 PASS**

---

### Phase 4 — Whisper STT 멀티모달

**목적**: 시각(YOLO+CLIP)만으로 세부 구분 안 되는 케이스를 음성 대사로 보완.

```
예시:
  CLIP: "해산물 요리" → 굴비인지 일반 생선인지 구분 불가
  STT:  "영광 굴비가 정말 맛있네요" → 굴비 광고 트리거 확정
```

#### 파이프라인

```
VOD 영상
    → audio_extractor.py (ffmpeg)
    → 16kHz mono WAV
    → stt_scorer.py (openai-whisper small)
    → [{start, end, text}, ...]
    → keyword_mapper.py
    → [{vod_id, start_ts, end_ts, keyword, ad_category, ad_hints, ...}]
    → vod_stt_concept.parquet
```

#### 키워드 → 복수 지역 설계 (`config/stt_keywords.yaml`)

```yaml
지방특산물:
  대게:
    ad_hints: ["영덕 대게 직송", "울진 대게 특가"]  # 복수 지역
  녹차:
    ad_hints: ["보성 녹차", "하동 녹차", "제주 녹차"]  # 3개 지역
```

Shopping_Ad가 사용자 실제 위치와 교차하여 최적 힌트 선택.
Object_Detection은 "어떤 특산물인지"만 판단하고, "어느 지역 것인지"는 Shopping_Ad 담당.

#### 구현 파일

| 파일 | 역할 |
|------|------|
| `src/audio_extractor.py` | ffmpeg subprocess → 16kHz mono WAV (임시파일, 처리 후 자동 삭제) |
| `src/stt_scorer.py` | `whisper.load_model("small")`, 한국어 강제(`language="ko"`) |
| `src/keyword_mapper.py` | yaml 키워드 로드, `keyword in transcript` 매칭, 복수 키워드 지원 |
| `scripts/batch_stt_score.py` | 배치 실행, 임시 WAV 정리, parquet 저장 |

#### 산출물 스키마 (`vod_stt_concept.parquet`)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `start_ts` | float | 발화 구간 시작 (초) |
| `end_ts` | float | 발화 구간 종료 (초) |
| `transcript` | str | 해당 구간 인식 텍스트 |
| `keyword` | str | 매칭된 키워드 |
| `ad_category` | str | 광고 카테고리 |
| `ad_hints` | str | 광고 힌트 (복수 중 랜덤 1개) |
| `region` | str | 시뮬레이션 지역명 |
| `sim_lat` | float | 시뮬레이션 위도 |
| `sim_lng` | float | 시뮬레이션 경도 |
| `context_valid` | bool | 광고 트리거 적합 여부 |
| `context_reason` | str | 판단 근거 |

#### 테스트: **12/12 PASS**

---

## 4. 전체 테스트 현황

```
tests/test_phase1_setup.py      13/13 PASS  ← YOLO 객체 탐지
tests/test_phase2_clip.py       13/13 PASS  ← CLIP 장면 인식
tests/test_phase3_ad_targeting.py  13/13 PASS  ← 광고 연동 + context_filter
tests/test_phase4_stt.py        12/12 PASS  ← Whisper STT
──────────────────────────────────────────
합계                            51/51 PASS ✅
```

---

## 5. Shopping_Ad 브랜치 인터페이스

Shopping_Ad는 아래 3개 파일을 소비하여 광고 매칭을 수행한다.

| 파일 | 조인 기준 | 주요 소비 컬럼 |
|------|---------|-------------|
| `vod_detected_object.parquet` | `vod_id + frame_ts` | `label` (식기류 체크 보조) |
| `vod_clip_concept.parquet` | `vod_id + frame_ts` | `ad_category`, `context_valid`, `ad_hints`, `region` |
| `vod_stt_concept.parquet` | `vod_id + [start_ts~end_ts]` | `keyword`, `ad_category`, `ad_hints` |

**광고 트리거 조건**:
- `context_valid=True` 레코드만 광고 매칭 대상
- CLIP 또는 STT 중 하나라도 `context_valid=True`면 트리거 후보
- 최종 광고 선택: `ad_category` + 사용자 실제 위치 → 지역 특산물 광고

---

## 6. 알려진 한계

| 인식 대상 | 한계 | 보완 방안 |
|---------|------|---------|
| 밀키트 패키지 | 시각적 특징 없음 | 제목/장르 메타데이터 활용 |
| 굴비 vs 일반 생선 | CLIP 단독으로 구분 어려움 | Phase 4 STT로 보완 |
| 유럽 세부 국가 | 프랑스 vs 이탈리아 불가 | 장르/제목 메타데이터 |
| 애니/게임 음식 | CLIP 인식 불안정 | negative secondary check 적용 |
| TV 화면 속 화면 | screen-in-screen 탐지 어려움 | 별도 로직 필요 (미구현) |

---

## 7. 커밋 이력

| 커밋 | 내용 |
|------|------|
| Phase 1 구현 | YOLO 파이프라인, 13/13 PASS |
| Phase 2 구현 | CLIP zero-shot, location_tagger |
| Phase 3 초기 | CLIP 쿼리 보강, context_filter, multilingual 모델 |
| KoCLIP A/B | 한국어 쿼리 + threshold 0.26 확정 |
| YOLO+CLIP 통합 | load_yolo_index, 실제 라벨 전달 |
| PLAN_03 개선 | 문서 품질 개선, Current Decision 박스 |
| context_filter 강화 | Brand Safety, secondary check, 성능 버그 수정 |
| Phase 4 구현 | Whisper STT 파이프라인, 51/51 PASS |
