# PLAN_02 — Object Detection 정확도 고도화 (단계별 실험)

- **브랜치**: Object_Detection
- **Phase**: Phase 3
- **작성일**: 2026-03-14

---

## 목표

**후속 브랜치(Shopping_Ad, 지역마켓)가 사용하기 좋은 객체/장면 태그를 parquet으로 생성한다.**

핵심 질문:
> "내 브랜치에서 어떤 비전 기술을 어느 순서로 붙여야
> 홈쇼핑/지역마켓 브랜치가 쓰기 좋은 결과가 나오나?"

---

## 현재 한계 (Phase 1 파일럿 기준)

| 필요한 것 | 현재 가능 여부 | 이유 |
|---------|-------------|------|
| 가전/가구 (TV, 냉장고, 침대) | ✅ 60% | COCO 포함 |
| 서양 음식 (피자, 케이크, 과일) | ✅ 부분 | COCO 포함 |
| **한식** (전골, 굴비, 대게) | ❌ | COCO 없음 |
| **장소/장면** (바다, 주방, 시장) | ❌ | object detection 범위 밖 |
| **지역성** (강원도, 전라도) | ❌ | 비전만으로 불가 — 메타데이터 보완 필요 |

---

## 기술 역할 정의

| 기술 | 역할 | 한계 |
|------|------|------|
| **YOLO11s** | 객체 위치(bbox) + 일반 사물 탐지 | COCO 80종 외 탐지 불가 |
| **CLIP zero-shot** | 프레임 전체 의미 판단 (장면/개념 유사도) | bbox 없음, 정밀 탐지 아님 |
| **Places365** | 장소 직접 분류 (beach, kitchen, market 등) | 객체 탐지 아님 |
| **제목/장르 결합** | 지역성·맥락 보완 | 영상만으로 못 잡는 것 보완 |
| **Grounding DINO** | 텍스트 기반 오픈 어휘 탐지 ("대게", "전골") | 느림, 설치 복잡 |

> **CLIP은 "다 해결"이 아니라 "장면 의미 실험/보완용"**
> **지역성(강원도, 전라도)은 비전만으로 불가 — 제목/장르 결합이 현실적**

---

## 단계별 로드맵 (Test-Driven)

### Phase 1 ✅ — YOLO11s Baseline

- 가전/가구/일반 사물 탐지
- parquet 저장 (`vod_id`, `frame_ts`, `label`, `confidence`, `bbox`)
- **완료 기준**: 13/13 테스트 PASS, 파일럿 10건 성공

---

### Phase 2 — CLIP Zero-shot 실험 (장면/개념 보완)

**목적**: YOLO가 못 잡는 장면·개념을 텍스트 쿼리로 보완

```python
# 예시 쿼리 목록
queries = [
    "바닷가", "전통시장", "주방", "야외 캠핑",     # 장소
    "해산물", "전골", "한식 식탁", "고기구이",      # 한식
    "가전제품", "냉장고", "소파",                   # 홈쇼핑 연동
]
# 프레임별 각 쿼리 유사도(0~1) 계산 → 임계값(예: 0.25) 이상만 저장
```

**산출물 추가 컬럼** (`vod_clip_concept.parquet`):

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `frame_ts` | float | 프레임 타임스탬프 |
| `concept` | str | CLIP 쿼리 텍스트 |
| `clip_score` | float | 유사도 점수 (0~1) |

**측정 지표**:
- 쿼리별 평균 clip_score
- 실제 예능 장면과 매칭 여부 육안 검증 (샘플 10건)

---

### Phase 3 — 제목/장르 메타데이터 결합 (지역성 보완)

**목적**: 영상만으로 못 잡는 지역성·맥락을 DB 정보로 보완

```python
# DB vod 테이블에서 asset_nm, genre, smry 가져와서 결합
# 예: "강원도 동해안 맛기행 3회" → 지역 태그 "강원도" 추출
# 예: genre="여행" → scene_hint="여행/야외" 추가
```

**산출물 추가 컬럼** (`vod_detected_object.parquet`에 병합):

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `region_hint` | str | 제목/장르에서 추출한 지역 힌트 |
| `scene_hint` | str | 장르 기반 장면 힌트 (여행/요리/토크) |

---

### Phase 4 — 필요 시 고도화 (결과 평가 후 결정)

| 옵션 | 조건 | 내용 |
|------|------|------|
| Places365 | 장소 분류 정확도 부족 | beach/kitchen/market 365종 직접 분류 |
| Grounding DINO | 한식 탐지 정확도 부족 | "굴비", "대게" 오픈 어휘 탐지 |
| YOLO fine-tuning | 특정 상품군 반복 오탐 | 한식/가전 도메인 커스텀 학습 |

---

## 후속 브랜치가 소비하는 산출물

| 파일 | 소비 브랜치 | 주요 컬럼 |
|------|-----------|---------|
| `vod_detected_object.parquet` | Shopping_Ad | `label`, `bbox`, `confidence` |
| `vod_clip_concept.parquet` | Shopping_Ad, 지역마켓 | `concept`, `clip_score` |
| `region_hint`, `scene_hint` (병합) | 지역마켓 | `region_hint`, `scene_hint` |

---

## Phase 2 완료 기준

- [ ] CLIP zero-shot 파이프라인 구현 (`src/clip_scorer.py`)
- [ ] 쿼리 목록 정의 (`config/clip_queries.yaml`)
- [ ] 파일럿 10건 실험 → clip_score 분포 확인
- [ ] YOLO + CLIP 결합 parquet 생성
- [ ] `tests/test_phase2_clip.py` PASS
- [ ] `docs/reports/phase2_clip_report.md` 작성
