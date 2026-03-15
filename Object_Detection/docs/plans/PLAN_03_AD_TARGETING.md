# PLAN_03 — 홈쇼핑·지방마켓 광고 연동 인식 확장

- **브랜치**: Object_Detection
- **Phase**: Phase 3
- **작성일**: 2026-03-15

---

## 프로젝트 의도 (공식 명세)

> 본 프로젝트는 영상 콘텐츠의 장면을 인식하여, 그 장면과 의미적으로 연결되는 광고를 노출하는 시스템을 목표로 한다.

### 지역 마켓 연동 핵심 원칙

**사용자 위치 기반이 아니라**, 영상 속 음식·식재료·먹는 장면을 인식해서
그와 관련된 지역 특산품 광고를 띄우는 방식이다.

```
영상 장면 분석 → 음식/객체 인식 → 관련 지역 특산품 매핑 → 로컬 광고 노출
```

### 현재 브랜치(Object_Detection) 구현 범위

전체 광고 연동 시스템을 완성하는 것이 아니라, **그 기반이 되는 객체 인식 기능만 구현**한다.

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

**2. 지방 마켓 연동 (영상 인식 기반)**

> ※ 사용자 위치는 별도 수집 — 이 브랜치는 "무엇이 등장하는지"만 태그로 출력

| 영상 장면 | 인식 태그 | 연동 광고 예시 |
|---------|---------|-------------|
| 굴비·조기 먹는 장면 | `dried_corvina_fish` | 영광 굴비 특가 |
| 대게 먹는 장면 | `snow_crab` | 영덕 대게 로컬 마켓 |
| 사과 먹는 장면 | `apple` (YOLO) | 예산 사과 농산물 광고 |
| 해산물 시장 장면 | `seafood_market` | 지역 수산물 마켓 |

---

## 현재 인식 가능 범위 (YOLO + CLIP)

### YOLO (COCO 80종 — 즉시 사용 가능)

| 카테고리 | 탐지 가능 항목 |
|---------|-------------|
| 과일·채소 | apple ✅, banana ✅, orange ✅, broccoli ✅, carrot ✅ |
| 가전 | tv ✅, laptop ✅, cell phone ✅, microwave ✅, refrigerator ✅ |
| 가구 | couch ✅, chair ✅, bed ✅, dining table ✅ |
| 사람/소품 | person ✅, handbag ✅, suitcase ✅ |

### CLIP (한국어 쿼리 + multilingual — threshold 0.27 적용 예정)

| 탐지 가능 | 탐지 불가 |
|---------|---------|
| 바닷가 해변 ✅ | 밀키트 패키지 ❌ (시각 특징 없음) |
| 한식·BBQ·해산물 ✅ | 유럽 세부 국가 구분 ❌ |
| 굴비 먹는 식사 장면 ✅ | 수조 금붕어 (context_filter로 차단) |
| 대게·장어·전복 ✅ | |
| 제주도·국내 여행지 ✅ | |
| 가전·가구 홈쇼핑 ✅ | |

---

## Phase 3 구현 계획

### Step 1 — CLIP 쿼리 보강 (즉시)

`config/clip_queries.yaml`에 아래 카테고리 추가:

```yaml
  지방특산물:
    - "dried fish Korean style gulbi corvina"
    - "snow crab seafood Korean"
    - "abalone shellfish Korean"
    - "Korean beef marbled wagyu"
    - "pineapple tropical fruit"
    - "mango tropical fruit"
    - "strawberry fresh fruit"
    - "fresh vegetable market produce"

  여행지:
    - "European city street architecture"
    - "tropical beach resort Southeast Asia Philippines"
    - "Mediterranean coast scenic"
    - "Japanese cherry blossom travel"
    - "domestic Korean island Jeju"

  홈쇼핑_확장:
    - "meal kit cooking package"
    - "health supplement vitamin product"
    - "cosmetics skincare beauty product"
    - "outdoor camping gear equipment"
```

### Step 2 — KoCLIP 전환 ✅ 실험 완료 (2026-03-15)

`jaketae/koclip`은 `setup.py` 미존재로 pip 설치 불가. 대신 `clip-ViT-B-32-multilingual-v1` 채택.

**아키텍처 (듀얼 모델)**:
```
이미지 프레임  →  clip-ViT-B-32            →  512차원 벡터
한국어 쿼리   →  clip-ViT-B-32-multilingual-v1  →  512차원 벡터 (동일 공간)
                                                ↓
                                         코사인 유사도
```

**A/B 실험 결과 (동일 VOD 10건)**:

| 지표 | EN (영어 + ViT-B-32) | KO (한국어 + multilingual) |
|------|---------------------|--------------------------|
| 총 태그 건수 | 1,385 | 3,871 |
| 고유 concept | 20/43 | 33/43 |
| clip_score std | 0.013 | 0.012 |
| threshold | 0.25 | 0.25 |

**판정**: std 거의 동일(판별력 동등). KO가 건수 2.8배 많음 → threshold 0.27로 조정 예정.

**채택 결정**: `clip-ViT-B-32-multilingual-v1` + 한국어 쿼리 + threshold **0.26** ✅ 확정

| threshold | 건수 | concept | 판정 |
|-----------|------|---------|------|
| KO th=0.25 | 3,871 | 33개 | 너무 많음 |
| EN th=0.25 | 1,385 | 20개 | 기준 |
| **KO th=0.26** | **1,925** | **23개** | **최적** |
| KO th=0.27 | 889 | 14개 | 너무 적음 |

`config/clip_queries.yaml` 한국어 쿼리로 교체 완료 (threshold 0.26, multilingual 모델 명시)

### Step 3 — 산출물 스키마 확장

현재 `vod_clip_concept.parquet` 에 `ad_category` 컬럼 추가:

| 컬럼 | 타입 | 예시 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `frame_ts` | float | 타임스탬프 |
| `concept` | str | "dried fish Korean style gulbi corvina" |
| `clip_score` | float | 0.283 |
| `ad_category` | str | `"지방특산물"` / `"여행지"` / `"홈쇼핑"` |

`ad_category`는 yaml의 카테고리 키에서 자동 부여.

---

## ⚠️ 광고 트리거 적합성 판단 (Context Filtering)

단순 객체 감지만으로는 **오탐(false trigger)** 이 발생한다.

> 예: 수조 안 금붕어 감지 → 굴비 광고 노출 → 최악의 UX

객체가 감지되었더라도 **장면 맥락이 광고 트리거에 적합한지** 판단하는 로직이 필요하다.

### 오탐 사례 및 필터링 규칙

| 감지된 객체 | 잘못된 트리거 | 맥락 필터 조건 |
|---------|------------|-------------|
| 금붕어 (수조) | 굴비/수산물 광고 | 식기류(plate/bowl/chopsticks) 없으면 차단 |
| 장식용 과일 | 과일 홈쇼핑 광고 | 먹는 행위(person+식기) 없으면 차단 |
| TV 화면 속 음식 | 음식 광고 | 중첩 감지 신뢰도 낮음 → 차단 |

### 구현 방법

**방법 1: 객체 조합 규칙 (YOLO)**

음식류 객체는 식기류와 함께 감지될 때만 광고 트리거로 인정.

```python
FOOD_LABELS = {"fish", "apple", "banana", "orange", ...}
TABLEWARE = {"fork", "knife", "spoon", "bowl", "cup", "dining table"}

def is_eating_scene(yolo_labels: set) -> bool:
    has_food = bool(FOOD_LABELS & yolo_labels)
    has_tableware = bool(TABLEWARE & yolo_labels)
    return has_food and has_tableware
```

**방법 2: CLIP 장면 쿼리 세분화**

```yaml
# 음식 트리거용 (맥락 포함)
- "person eating fish meal at dining table"
- "grilled fish on plate Korean food"

# Negative 맥락 (광고 차단)
- "goldfish aquarium pet tank"        ← 이 쿼리가 높으면 생선 광고 차단
- "decorative fruit bowl centerpiece" ← 이 쿼리가 높으면 과일 광고 차단
```

**방법 3: 장면 신뢰도 조합**

```python
# YOLO + CLIP 교차 검증
# YOLO: "생선 감지" AND CLIP: "eating scene" 둘 다 충족할 때만 트리거
trigger = yolo_has_fish and clip_score("person eating fish meal") > threshold
```

### 산출물에 추가될 컬럼

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `context_valid` | bool | 광고 트리거 적합 여부 |
| `context_reason` | str | 판단 근거 ("eating_scene", "aquarium_filtered" 등) |

Shopping_Ad는 `context_valid=True`인 레코드만 광고 매칭에 사용한다.

---

## 탐지 한계 및 보완 방안

| 인식 대상 | 한계 | 보완 |
|---------|------|------|
| 밀키트 패키지 | 시각적 특징 없음 | 제목/장르 메타데이터 활용 |
| 지역 특산품 세부 구분 | 굴비 vs 일반 생선 구분 어려움 | KoCLIP + 더 세밀한 쿼리 |
| 유럽 세부 국가 | 프랑스 vs 이탈리아 구분 불가 | 장르/제목 메타데이터 보완 |
| COCO 미포함 과일 | 파인애플, 망고 | CLIP 쿼리로 보완 |

---

## 후속 브랜치 인터페이스 (Shopping_Ad 소비)

| 파일 | 주요 컬럼 | 용도 |
|------|---------|------|
| `vod_detected_object.parquet` | `label`, `confidence`, `bbox` | YOLO 객체 탐지 결과 |
| `vod_clip_concept.parquet` | `concept`, `clip_score`, `ad_category` | CLIP 장면/개념 태그 |

Shopping_Ad는 두 파일을 `vod_id` + `frame_ts` 기준으로 조인하여 광고 후보를 선정한다.

---

## Phase 4 — Whisper STT 멀티모달 확장 (추후)

> Phase 3 완료 후 진행. 현재 브랜치 범위에 포함하되 시각 인식 완성 후 착수.

### 목적

시각(YOLO+CLIP)만으로 해결 안 되는 세부 구분을 **대사/음성**으로 보완.

```
영상: 생선 먹는 장면 (CLIP: "fish meal" 수준)
오디오: "영광 굴비가 정말 맛있네요"
→ 굴비 광고 트리거 ← 정확도 대폭 향상
```

### 기술 스택

| 기술 | 역할 |
|------|------|
| `openai-whisper` | 한국어 STT (대사 → 텍스트) |
| 키워드 매핑 dict | "굴비" → `ad_category=지방특산물` |

### 추가될 산출물 컬럼

| 컬럼 | 타입 | 예시 |
|------|------|------|
| `stt_text` | str | "오늘은 영광 굴비를 먹어볼게요" |
| `stt_keywords` | list | `["굴비", "영광"]` |
| `stt_ad_hint` | str | `"지방특산물"` |

### 기대 효과

| 한계 | 시각만 | 시각+STT |
|------|--------|---------|
| 굴비 vs 고등어 구분 | ❌ | ✅ 대사로 직접 |
| 지역명 언급 | ❌ | ✅ "영광", "영덕" |
| 음식명 직접 언급 | ❌ | ✅ |

---

## 완료 기준

- [x] CLIP 쿼리 보강 (`config/clip_queries.yaml`) — 지방특산물·여행지·과일채소·negative 추가
- [x] `ad_category` 컬럼 산출물 추가
- [x] 파일럿 10건 재실험 → 1,453건, 5개 ad_category 탐지 확인
- [x] KoCLIP 전환 실험 — multilingual A/B 비교 완료 (std 동등, KO 채택)
- [x] threshold 실험 (0.25→0.26→0.27) → **0.26 최종 채택**
- [x] `config/clip_queries.yaml` → 한국어 쿼리로 교체 (threshold 0.26, multilingual 모델)
- [ ] `docs/reports/phase3_ad_targeting_report.md` 작성
