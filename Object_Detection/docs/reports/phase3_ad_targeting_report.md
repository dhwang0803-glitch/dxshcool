> ⚠️ **OUTDATED**: 홈쇼핑 8종 → 제철장터+지자체 2종으로 전략 변경 (2026-03-19).
> 최신 → `docs/MATCHING_FLOW.md`

# Phase 3 리포트 — 홈쇼핑·지방마켓 광고 연동 인식 확장

- **작성일**: 2026-03-15
- **작성자**: 박아름
- **브랜치**: Object_Detection
- **참조 계획**: `docs/plans/PLAN_03_AD_TARGETING.md`

---

## 개요

Phase 3에서는 Phase 2(CLIP zero-shot 파일럿)의 결과를 바탕으로 세 가지 작업을 완료했다.

1. CLIP 쿼리 보강 — 지방특산물·과일채소·여행지·negative 카테고리 추가
2. KoCLIP A/B 실험 — multilingual 한국어 쿼리 최적 모델·threshold 확정
3. YOLO+CLIP 통합 — `context_filter`에 실제 YOLO 라벨 전달 (식기류 체크 활성화)

산출물 `vod_clip_concept.parquet`이 Shopping_Ad 브랜치의 광고 매칭 입력으로 사용된다.

---

## 최종 확정 설정

| 항목 | 확정값 |
|------|--------|
| 이미지 모델 | `clip-ViT-B-32` |
| 텍스트 모델 | `clip-ViT-B-32-multilingual-v1` |
| 쿼리 언어 | 한국어 (`config/clip_queries.yaml`) |
| threshold | **0.26** |
| 구현 파일 | `src/clip_scorer.py`, `src/context_filter.py`, `scripts/batch_clip_score.py` |

---

## Step 1 — CLIP 쿼리 보강

`config/clip_queries.yaml`에 4개 카테고리 추가:

| 카테고리 | 쿼리 수 | 주요 항목 |
|---------|--------|---------|
| `지방특산물` | 7개 | 굴비, 대게, 전복, 한우, 젓갈, 굴, 장어 |
| `과일채소` | 6개 | 파인애플, 망고, 딸기, 채소, 수박, 포도 |
| `여행지` | 6개 | 유럽, 동남아, 지중해, 일본, 제주도, 국내시골 |
| `negative` | 3개 | 금붕어 수조, 장식용 과일, 물고기 그림 (오탐 차단용) |

---

## Step 2 — KoCLIP A/B 실험

### 배경

Phase 2에서 영어 쿼리 + `clip-ViT-B-32` 조합이 판별력(std=0.013) 측면에서 우수했으나,
한국 특산물(굴비, 대게 등) 표현 정확도와 팀 관리 편의를 위해 한국어 쿼리 전환 가능성을 검토했다.

`jaketae/koclip`은 pip 설치 불가(setup.py 미존재) → `clip-ViT-B-32-multilingual-v1` 대체 채택.
multilingual 모델은 텍스트 전용 → 이미지 인코딩 불가 → **듀얼 모델 구조** 채택.

```
이미지 프레임  →  clip-ViT-B-32                →  512차원 벡터
한국어 쿼리   →  clip-ViT-B-32-multilingual-v1  →  512차원 벡터 (동일 공간)
                                                  ↓
                                           코사인 유사도
```

### 실험 결과 — 동일 VOD 10건 공정 비교

| 설정 | 총 건수 | 고유 concept | clip_score std |
|------|--------|-------------|----------------|
| EN (`clip-ViT-B-32`, th=0.25) | 1,385 | 20/43개 | **0.013** |
| KO (`multilingual`, th=0.25) | 3,871 | 33/43개 | 0.012 |
| **KO (`multilingual`, th=0.26)** | **1,925** | **23/43개** | **0.012** |
| KO (`multilingual`, th=0.27) | 889 | 14/43개 | — |

### 채택 결정

**`clip-ViT-B-32-multilingual-v1` + 한국어 쿼리 + threshold 0.26**

- 판별력(std): EN 0.013 ≈ KO 0.012 → **사실상 동등**
- concept 커버리지: KO 23개 > EN 20개 → **KO 우위**
- 건수: KO 1,925 vs EN 1,385 → threshold 0.26으로 제어
- 한국 특산물("굴비 먹는 식사 장면", "대게 해산물", "장어구이") KO 쿼리에서 직접 탐지 가능

---

## Step 3 — YOLO+CLIP 통합

### 문제

Phase 2~3 파일럿에서 `batch_clip_score.py`가 `yolo_labels=set()` 빈값을 `context_filter.validate()`에 전달하고 있었다.
`context_filter`의 식기류 체크 로직(음식 + 식기류 동반 여부)이 실질적으로 비활성화된 상태였다.

### 구현

`batch_clip_score.py`에 `load_yolo_index()` 함수 추가:

```python
def load_yolo_index(yolo_path: Path) -> dict:
    """vod_detected_object.parquet → {vod_id: {frame_ts: set(labels)}}"""
    if not yolo_path.exists():
        return {}  # 파일 없으면 빈 dict → CLIP 단독 실행 유지
    df = pd.read_parquet(str(yolo_path))
    index: dict = {}
    for row in df.itertuples(index=False):
        ts = round(float(row.frame_ts), 3)
        index.setdefault(row.vod_id, {}).setdefault(ts, set()).add(row.label)
    return index
```

- `--yolo-parquet` CLI 옵션 추가 (기본값: `data/vod_detected_object.parquet`)
- `vod_detected_object.parquet` 없으면 빈 set 폴백 → 기존 CLIP 단독 실행 동작 유지
- 타임스탬프 일치 보장: 두 스크립트 모두 `extract_frames(..., fps=1.0)`으로 `round(idx/video_fps, 3)` 사용

### context_filter 동작 (활성화 후)

| 조건 | context_valid | 이유 |
|------|--------------|------|
| 음식 탐지 + 식기류(fork/bowl/chopsticks 등) 동반 | True | `eating_scene` |
| 음식 탐지 + 식기류 없음 | False | `no_tableware_with_food` |
| negative 쿼리(금붕어/수조) 최고점 | False | `aquarium_filtered:...` |
| 홈쇼핑/여행지 등 비음식 카테고리 | True | `non_food_category` |

---

## 산출물 스키마 (`vod_clip_concept.parquet`)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `frame_ts` | float | 프레임 타임스탬프 (초) |
| `concept` | str | 매칭된 한국어 쿼리 텍스트 |
| `clip_score` | float | 코사인 유사도 (0.0~1.0) |
| `ad_category` | str | yaml 카테고리 키 (한식/지방특산물/홈쇼핑 등) |
| `context_valid` | bool | 광고 트리거 적합 여부 |
| `context_reason` | str | 판단 근거 |
| `region` | str | 시뮬레이션 지역명 |
| `ad_hints` | str | 지역별 광고 힌트 |
| `sim_lat` | float | 시뮬레이션 위도 |
| `sim_lng` | float | 시뮬레이션 경도 |

Shopping_Ad는 `context_valid=True` 레코드만 광고 매칭에 사용한다.
`vod_detected_object.parquet`과 `vod_id + frame_ts` 기준으로 조인.

---

## 탐지 한계

| 대상 | 한계 | 보완 방안 |
|------|------|---------|
| 밀키트 패키지 | 시각적 특징 없음 | 제목/장르 메타데이터 활용 |
| 지역 특산품 세부 구분 | 굴비 vs 일반 생선 구분 어려움 | Phase 4 STT 보완 |
| 유럽 세부 국가 구분 | 프랑스 vs 이탈리아 불가 | 장르/제목 메타데이터 보완 |

---

## TDD 결과

```
37/37 PASS (Phase 1~3 전체)
```

---

## 다음 단계

| 작업 | 상태 |
|------|------|
| Phase 4 — Whisper STT 멀티모달 확장 | 🔲 추후 |
| Shopping_Ad 브랜치 연동 | 🔲 parquet 스키마 전달 완료, 브랜치 착수 대기 |
