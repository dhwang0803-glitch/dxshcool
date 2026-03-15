# PLAN_03 — 홈쇼핑·지방마켓 광고 연동 인식 확장

- **브랜치**: Object_Detection
- **Phase**: Phase 3
- **작성일**: 2026-03-15

---

## ✅ Current Decision (단일 기준값)

| 항목 | 확정값 |
|------|--------|
| 이미지 모델 | `clip-ViT-B-32` |
| 텍스트 모델 | `clip-ViT-B-32-multilingual-v1` |
| 쿼리 언어 | 한국어 (`config/clip_queries.yaml`) |
| threshold | **0.26** |
| 구현 파일 | `src/clip_scorer.py`, `src/context_filter.py`, `scripts/batch_clip_score.py` |

---

## 프로젝트 의도 (공식 명세)

> 본 프로젝트는 영상 콘텐츠의 장면을 인식하여, 그 장면과 의미적으로 연결되는 광고를 노출하는 시스템을 목표로 한다.

### 지역 마켓 연동 핵심 원칙

**영상 인식 + 사용자 위치** 두 가지를 모두 활용한다.

```
영상 장면 분석 → 음식/객체 인식 → 광고 카테고리 트리거
                                        ↓
                              사용자 위치 결합
                                        ↓
                         해당 지역 특산품 광고 노출
```

| 역할 | 담당 |
|------|------|
| 광고 트리거 (언제 띄울지) | **영상 인식** — 굴비 먹는 장면 감지 → 지방특산물 광고 타이밍 |
| 광고 선택 (무엇을 띄울지) | **사용자 위치** — 전남 사용자 → 영광 굴비 / 경북 사용자 → 영덕 대게 |

> parquet 산출물의 `region`, `ad_hints`, `sim_lat`, `sim_lng` 컬럼이 위치 기반 광고 선택에 사용됨.
> 실제 사용자 위치는 Shopping_Ad에서 주입 — Object_Detection은 위치 시뮬레이션만 담당.

### 현재 브랜치(Object_Detection) 구현 범위

| 구현 범위 | 담당 |
|---------|------|
| 영상 프레임 추출 | ✅ 이 브랜치 |
| 객체 탐지 모델 기반 인식 | ✅ 이 브랜치 |
| 탐지 결과 저장 (parquet) | ✅ 이 브랜치 |
| 홈쇼핑 광고 매칭 | ❌ Shopping_Ad 브랜치 |
| 지역 특산품 광고 매칭 | ❌ Shopping_Ad 브랜치 |

---

## 목표

Object_Detection 브랜치는 **영상에서 객체·장면을 인식해 태그를 생성**하는 역할을 담당한다.
이 태그를 Shopping_Ad 브랜치가 소비하여 실제 광고를 연동한다.

### 연동 시나리오

**1. 홈쇼핑 실시간 연동 (콘텐츠 문맥 기반)**

| 영상 장면 | 인식 태그 | 연동 광고 예시 |
|---------|---------|-------------|
| 파인애플 등장 | `pineapple` | 파인애플 특가 홈쇼핑 |
| 바다·해변 장면 | `tropical_beach` | 필리핀 여행 패키지 |
| 유럽 거리 배경 | `european_city` | 유럽 패키지 여행 |
| 소파·TV 등장 | `furniture`, `appliance` | 가구·가전 홈쇼핑 |
| 한식 밥상 | `korean_food` | 밀키트·식품 홈쇼핑 |

**2. 지방 마켓 연동 (영상 인식 + 위치 기반)**

| 영상 장면 | 인식 태그 | 연동 광고 예시 |
|---------|---------|-------------|
| 굴비·조기 먹는 장면 | `dried_corvina_fish` | 영광 굴비 특가 |
| 대게 먹는 장면 | `snow_crab` | 영덕 대게 로컬 마켓 |
| 사과 먹는 장면 | `apple` (YOLO) | 예산 사과 농산물 광고 |
| 해산물 시장 장면 | `seafood_market` | 지역 수산물 마켓 |

---

## 현재 인식 가능 범위 (YOLO + CLIP)

### YOLO (COCO 80종 — 구현 완료 ✅)

| 카테고리 | 탐지 가능 항목 |
|---------|-------------|
| 과일·채소 | apple ✅, banana ✅, orange ✅, broccoli ✅, carrot ✅ |
| 가전 | tv ✅, laptop ✅, cell phone ✅, microwave ✅, refrigerator ✅ |
| 가구 | couch ✅, chair ✅, bed ✅, dining table ✅ |
| 사람/소품 | person ✅, handbag ✅, suitcase ✅ |

### CLIP (한국어 쿼리 + multilingual, threshold 0.26 — 구현 완료 ✅)

| 탐지 가능 | 탐지 불가 |
|---------|---------|
| 바닷가 해변 ✅ | 밀키트 패키지 ❌ (시각 특징 없음) |
| 한식·BBQ·해산물 ✅ | 유럽 세부 국가 구분 ❌ |
| 굴비 먹는 식사 장면 ✅ | 수조 금붕어 (context_filter로 차단) |
| 대게·장어·전복 ✅ | |
| 제주도·국내 여행지 ✅ | |
| 가전·가구 홈쇼핑 ✅ | |

---

## Phase 3 구현 내역

### Step 1 — CLIP 쿼리 보강 ✅ Done

`config/clip_queries.yaml`에 카테고리 추가 완료:
- `지방특산물`: 굴비, 대게, 전복, 한우, 젓갈, 굴, 장어 (7개)
- `과일채소`: 파인애플, 망고, 딸기, 채소, 수박, 포도 (6개)
- `여행지`: 유럽, 동남아, 지중해, 일본, 제주도, 국내시골 (6개)
- `negative`: 금붕어 수조, 장식 과일, 물고기 그림 (3개)

### Step 2 — multilingual 모델 도입 ✅ Done

> **주의**: `jaketae/koclip`은 pip 설치 불가(setup.py 미존재). `clip-ViT-B-32-multilingual-v1`로 대체 채택.

**아키텍처 (듀얼 모델)**:
```
이미지 프레임  →  clip-ViT-B-32                →  512차원 벡터
한국어 쿼리   →  clip-ViT-B-32-multilingual-v1  →  512차원 벡터 (동일 공간)
                                                  ↓
                                           코사인 유사도
```

**A/B 실험 결과 (동일 VOD 10건, threshold 조정 포함)**:

| 설정 | 건수 | concept | std | 판정 |
|------|------|---------|-----|------|
| EN th=0.25 | 1,385 | 20개 | 0.013 | 기준 |
| KO th=0.25 | 3,871 | 33개 | 0.012 | 너무 많음 |
| **KO th=0.26** | **1,925** | **23개** | 0.012 | **최적 ← 채택** |
| KO th=0.27 | 889 | 14개 | — | 너무 적음 |

**채택 근거**: 판별력(std) 동등, concept 커버리지 우위(23 vs 20), 한국어 쿼리가 팀 관리 측면에서 직관적.

### Step 3 — 산출물 스키마 확장 ✅ Done

**구현 완료 컬럼** (`vod_clip_concept.parquet`):

| 컬럼 | 타입 | 상태 | 설명 |
|------|------|------|------|
| `vod_id` | str | ✅ | VOD 식별자 |
| `frame_ts` | float | ✅ | 프레임 타임스탬프 |
| `concept` | str | ✅ | 매칭된 쿼리 텍스트 |
| `clip_score` | float | ✅ | 유사도 점수 |
| `ad_category` | str | ✅ | 카테고리 자동 부여 (yaml 키) |
| `context_valid` | bool | ✅ | 광고 트리거 적합 여부 |
| `context_reason` | str | ✅ | 판단 근거 |
| `region` | str | ✅ | 시뮬레이션 지역 |
| `ad_hints` | str | ✅ | 지역별 광고 힌트 |
| `sim_lat` | float | ✅ | 시뮬레이션 위도 |
| `sim_lng` | float | ✅ | 시뮬레이션 경도 |

---

## ⚠️ 광고 트리거 적합성 판단 (Context Filtering) ✅ Done

### 오탐 사례 및 필터링 규칙

| 감지된 객체 | 잘못된 트리거 | 맥락 필터 조건 |
|---------|------------|-------------|
| 금붕어 (수조) | 굴비/수산물 광고 | 식기류(plate/bowl/chopsticks) 없으면 차단 |
| 장식용 과일 | 과일 홈쇼핑 광고 | 먹는 행위(person+식기) 없으면 차단 |
| TV 화면 속 음식 | 음식 광고 | 중첩 감지 신뢰도 낮음 → 차단 |

**구현**: `src/context_filter.py`
- 음식류 카테고리(지방특산물/한식/과일채소)만 필터 적용
- YOLO 식기류 없이 음식만 탐지 → `context_valid=False`
- negative CLIP 쿼리 최고점 → `context_valid=False`
- 홈쇼핑/여행지 → 필터 미적용

> **구현 완료**: `batch_clip_score.py`에 `load_yolo_index()` 추가. `--yolo-parquet` 옵션으로
> `vod_detected_object.parquet`을 로드하여 프레임별 실제 YOLO 라벨을 `context_filter.validate()`에 전달.
> `vod_detected_object.parquet` 없으면 빈 set 폴백 (CLIP 단독 실행 유지).

Shopping_Ad는 `context_valid=True`인 레코드만 광고 매칭에 사용한다.

---

## 탐지 한계 및 보완 방안

| 인식 대상 | 한계 | 보완 |
|---------|------|------|
| 밀키트 패키지 | 시각적 특징 없음 | 제목/장르 메타데이터 활용 |
| 지역 특산품 세부 구분 | 굴비 vs 일반 생선 구분 어려움 | 더 세밀한 쿼리 + Phase 4 STT |
| 유럽 세부 국가 | 프랑스 vs 이탈리아 구분 불가 | 장르/제목 메타데이터 보완 |
| COCO 미포함 과일 | 파인애플, 망고 | CLIP 쿼리로 보완 (완료) |

---

## 후속 브랜치 인터페이스 (Shopping_Ad 소비)

| 파일 | 주요 컬럼 | 용도 |
|------|---------|------|
| `vod_detected_object.parquet` | `label`, `confidence`, `bbox` | YOLO 객체 탐지 결과 |
| `vod_clip_concept.parquet` | `concept`, `clip_score`, `ad_category`, `context_valid`, `region`, `ad_hints` | CLIP 장면/개념 태그 + 위치 |

Shopping_Ad는 두 파일을 `vod_id` + `frame_ts` 기준으로 조인하여 광고 후보를 선정한다.

---

## Phase 4 — Whisper STT 멀티모달 확장 `[Planned]`

> Phase 3 완료 후 진행.

시각(YOLO+CLIP)만으로 해결 안 되는 세부 구분을 **대사/음성**으로 보완.

```
영상: 생선 먹는 장면 (CLIP: "fish meal" 수준)
오디오: "영광 굴비가 정말 맛있네요"
→ 굴비 광고 트리거 ← 정확도 대폭 향상
```

| 기술 | 역할 |
|------|------|
| `openai-whisper` | 한국어 STT (대사 → 텍스트) |
| 키워드 매핑 dict | "굴비" → `ad_category=지방특산물` |

---

## 완료 기준

### 코드 구현 기준

- [x] CLIP 쿼리 보강 (`config/clip_queries.yaml`) — 지방특산물·여행지·과일채소·negative 추가
- [x] `ad_category` 컬럼 산출물 추가 (`clip_scorer.py`)
- [x] `context_filter.py` 구현 — 오탐 차단 로직
- [x] multilingual 듀얼 모델 지원 (`clip_scorer.py`)
- [x] `--model`, `--config` 옵션 추가 (`batch_clip_score.py`)
- [x] 한국어 쿼리 + threshold 0.26 확정 및 config 교체
- [x] YOLO + CLIP 통합 — `batch_clip_score.py`에 실제 yolo_labels 전달 (`load_yolo_index` + `--yolo-parquet` 옵션)

### 문서 기준

- [x] PLAN_03_AD_TARGETING.md 작성
- [x] session_report_20260315.md — KoCLIP A/B 실험 기록
- [ ] `docs/reports/phase3_ad_targeting_report.md` 작성 `[진행 예정]`
