# Object_Detection 세션 리포트 (2026-03-15) — Phase 2 CLIP 실험

- 작성일: 2026-03-15
- 작성자: 박아름
- 브랜치: Object_Detection

---

## 세션 요약

Phase 2 CLIP zero-shot 파일럿 실험 2종 (threshold 0.27 / 영어 쿼리 A/B 테스트).
threshold 최적화 및 영어 쿼리 전환 효과 검증. Phase 2 리포트 작성 완료.

---

## 완료 작업

### 1. CLIP 파일럿 재실험 — threshold 0.27

기존 threshold 0.22 실험 결과가 식별력 없음(23,345건, std=0.009)을 확인.
`config/clip_queries.yaml` threshold를 0.22 → 0.27로 상향 조정 후 재실험.

| 지표 | 0.22 (이전) | 0.27 (재실험) |
|------|------------|--------------|
| 총 태그 건수 | 23,345건 | 6,996건 |
| VOD당 평균 | ~2,335건 | ~700건 |
| clip_score 평균 | 0.244 | 0.284 |
| clip_score std | — | 0.009 |
| 고유 concept | 21/21 | 21/21 |

**문제**: std=0.009로 여전히 점수 분포가 좁음. 21/21 concept 전부 통과. 한국어 쿼리의 구조적 판별력 한계.

---

### 2. 영어 쿼리 A/B 테스트 준비

한국어 쿼리 판별력 한계 원인 분석:
- CLIP ViT-B/32는 영어 사전학습 모델 → 한국어 유사도 공간이 압축
- 동일 모델에서 영어 쿼리 사용 시 판별력 향상 기대

**방법 1 (영어 쿼리)**: config만 변경, 즉시 적용 가능
**방법 2 (KoCLIP)**: 한국어 fine-tuning 모델, 중장기 전환 권장

`config/clip_queries.yaml` 쿼리를 한국어 → 영어로 전환:

| 카테고리 | 한국어 예시 | 영어 변환 |
|---------|-----------|---------|
| 장소 | "바닷가" | "beach seaside ocean" |
| 한식 | "전골 찌개" | "Korean stew hot pot bubbling" |
| 홈쇼핑 | "가전제품" | "home appliance electronics TV" |

출력 파일을 `vod_clip_concept_en.parquet`으로 분리해 한국어 결과(`_kr`)와 병렬 비교 예정.

---

### 3. phase2_clip_report.md 작성

`docs/reports/phase2_clip_report.md` 생성:
- 실험 1/2 수치 비교
- 판별력 한계 원인 분석
- 후속 브랜치 권장 소비 방식 (최고점 concept 채택)
- Phase 3 계획 (제목/장르 메타데이터 결합)

#### 영어 쿼리 실험 결과 (threshold 0.27)

```
총 태그 건수: 86건
고유 concept: 8/21개
```

| concept | 건수 |
|---------|------|
| Korean food dining table | 65 |
| kitchen cooking indoors | 8 |
| Korean traditional food banchan | 4 |
| Korean stew hot pot bubbling | 4 |
| home appliance electronics TV | 2 |
| Korean BBQ grilled meat | 1 |
| seafood Korean cuisine | 1 |
| grilled fish Korean style | 1 |

| 지표 | 한국어 쿼리 | 영어 쿼리 |
|------|-----------|---------|
| 총 건수 | 6,996 | **86** |
| mean | 0.284 | 0.279 |
| std | 0.009 | **0.007** |
| max | 0.331 | 0.300 |
| 통과 concept | 21/21 | **8/21** |

**판정**: 영어 쿼리가 정밀도 측면에서 압도적 우위.
- 21/21 → 8/21 concept: 실제 콘텐츠와 무관한 concept 차단
- 6,996 → 86건: 노이즈 82배 감소
- 다만 8.6건/VOD로 **커버리지 과소** → threshold 0.25로 낮춰 재실험

#### 영어 쿼리 실험 결과 (threshold 0.25)

```
총 태그 건수: 133건
고유 concept: 9/21개
```

| concept | 건수 |
|---------|------|
| Korean food dining table | 96 |
| seafood Korean cuisine | 14 |
| home appliance electronics TV | 6 |
| Korean BBQ grilled meat | 5 |
| Korean traditional food banchan | 5 |
| Korean stew hot pot bubbling | 3 |
| mountain hiking trail | 2 |
| bedding blanket pillow bedroom | 1 |
| beach seaside ocean | 1 |

| 지표 | th=0.27 | th=0.25 |
|------|---------|---------|
| 총 건수 | 86 | **133** |
| concept | 8/21 | **9/21** |
| VOD당 평균 | 8.6건 | **13.3건** |

**판정**: threshold 0.25가 커버리지·정밀도 균형이 가장 나음.
- `beach seaside ocean`, `mountain hiking trail` 신규 진입 — 다양성 소폭 증가
- `Korean food dining table` 96/133 = 72% 쏠림은 여전히 존재
- 근본적 쏠림 해소는 KoCLIP(방법 2) 전환으로 해결 필요
- **최종 채택 threshold: 0.25 (영어 쿼리 기준)**

---

## 한계 및 발견 사항

| 항목 | 내용 |
|------|------|
| CLIP 한국어 판별력 | ViT-B/32 한국어 쿼리에서 concept 간 점수 차 ≤0.01 |
| threshold 효과 | 23k→7k 노이즈 제거는 유효, 개념 간 구분은 여전히 약함 |
| 실용적 활용 방향 | 프레임별 최고점 1~3개 concept 채택 권장 |

---

## Phase 3 구현 완료

### Step 1 — CLIP 쿼리 보강

`config/clip_queries.yaml` 3개 카테고리 추가:
- `지방특산물`: dried fish, snow crab, abalone, Korean beef, oyster, eel 등 7개
- `과일채소`: pineapple, mango, strawberry, watermelon, grape 등 6개
- `여행지`: European city, Southeast Asia, Mediterranean, Japan, Jeju 등 6개
- `negative`: goldfish aquarium, decorative fruit, painting 등 3개 (오탐 차단)

### Step 2 — ad_category 컬럼 추가

`clip_scorer.to_records()`에 `query_category_map` 파라미터 추가.
yaml 카테고리 키가 자동으로 `ad_category` 컬럼에 부여됨.
`negative` 카테고리는 records에서 자동 제외.

### Step 3 — context_filter 구현

`src/context_filter.py` 신규 생성:
- 음식류 카테고리만 필터 적용 (지방특산물/한식/과일채소)
- YOLO 식기류 없이 음식만 탐지 → `context_valid=False`
- negative CLIP 쿼리 최고점 → `context_valid=False`
- 홈쇼핑/여행지 등 비음식 카테고리 → 필터 미적용

### 파일럿 실험 결과 (Phase 3, threshold 0.25)

```
총 태그 건수: 1,453건 / 10 VOD
고유 concept: 20개
```

| ad_category | context_valid | 건수 |
|-------------|--------------|------|
| 한식 | True | 826 |
| 지방특산물 | True | 452 |
| 여행지 | True | 147 |
| 장소 | True | 17 |
| 홈쇼핑 | True | 11 |

산출물 컬럼: `vod_id`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid`, `context_reason`, `region`, `ad_hints`, `sim_lat`, `sim_lng`

### TDD 결과

```
37/37 PASS (Phase 1~3 전체)
```

## 다음 단계

| 작업 | 상태 |
|------|------|
| KoCLIP 모델 전환 | 🔲 예정 |
| Phase 4 — Whisper STT 멀티모달 | 🔲 추후 |
| Shopping_Ad 브랜치 연동 | 🔲 스키마 전달 후 |
