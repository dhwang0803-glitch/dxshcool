# Phase 2 리포트 — CLIP Zero-shot 실험 결과

- **브랜치**: Object_Detection
- **작성일**: 2026-03-15
- **작성자**: 박아름
- **관련 PLAN**: `docs/plans/PLAN_02_ACCURACY.md` (Phase 2)

---

## 1. 실험 목적

YOLO(COCO 80종)가 탐지 불가한 **한식·장면·장소 개념**을 CLIP zero-shot으로 보완한다.

---

## 2. 실험 환경

| 항목 | 값 |
|------|----|
| 모델 | `clip-ViT-B-32` (sentence-transformers/clip-ViT-B-32-multilingual-v1 fallback) |
| 쿼리 수 | 21개 (장소 9 / 한식 7 / 홈쇼핑 5) |
| 샘플 | 랜덤 10건 (`trailers_아름`) |
| fps | 1.0 |
| 실험 1 threshold | 0.22 |
| 실험 2 threshold | 0.27 |

---

## 3. 실험 1 — threshold 0.22

| 지표 | 값 |
|------|----|
| 총 태그 건수 | 23,345건 |
| VOD당 평균 | ~2,335건 |
| 고유 concept | 21/21 |
| clip_score 평균 | 0.244 |
| clip_score 범위 | 0.220 ~ 0.317 |

**판정**: threshold가 너무 낮아 거의 모든 프레임이 모든 쿼리를 통과. 식별력 없음.

---

## 4. 실험 2 — threshold 0.27 (채택)

| 지표 | 값 |
|------|----|
| 총 태그 건수 | 6,996건 |
| VOD당 평균 | ~700건 |
| 고유 concept | 21/21 |
| clip_score 평균 | 0.284 |
| clip_score std | **0.009** (매우 좁음) |
| clip_score 범위 | 0.270 ~ 0.331 |

### 상위 concept (빈도)

| concept | 건수 |
|---------|------|
| 농촌 시골 | 508 |
| 여행 패키지 | 480 |
| 어시장 수산물 | 453 |
| 가전제품 | 446 |
| 침구 이불 | 445 |
| 수산물 해산물 | 431 |
| 주방용품 | 429 |
| 고기구이 바베큐 | 422 |
| 전골 찌개 | 418 |
| 야외 캠핑 | 400 |

### 지역 분포 (랜덤 시뮬레이션)

| 지역 | 건수 |
|------|------|
| 기타 | 5,190 |
| 강원도 | 1,314 |
| 전라북도 | 492 |

---

## 5. 핵심 한계 및 분석

### 5-1. 판별력 부족 (std=0.009)

threshold 0.27에서 점수 분포가 0.270~0.331에 극도로 좁게 밀집. 모든 21개 concept이 전원 통과하는 구조. 이는 **clip-ViT-B-32 한국어 쿼리의 구조적 한계**:

- ViT-B/32는 영어 사전학습 기반 — 한국어 쿼리 유사도 공간이 압축됨
- 다국어 모델(multilingual-v1)도 한국어 세부 개념 분리 어려움
- "바닷가"와 "주방 요리"의 점수 차이가 0.01 미만

### 5-2. 실용적 사용 방향

완전한 이진 태그(pass/fail)보다 **상대 순위 활용** 권장:

```python
# 프레임별 최고점 1개 concept만 채택
df_top = df.loc[df.groupby(['vod_id','frame_ts'])['clip_score'].idxmax()]

# 또는 상위 N개
df_topN = df.sort_values('clip_score', ascending=False).groupby(['vod_id','frame_ts']).head(3)
```

### 5-3. 후속 브랜치(Shopping_Ad) 권장 소비 방식

| 소비 방식 | 설명 |
|----------|------|
| 최고점 concept | 프레임별 1위 concept → 광고 카테고리 매핑 |
| 상위 3개 concept | concept 앙상블로 광고 후보 확장 |
| threshold 미적용 | 전체 점수 활용, 정규화 후 가중합 |

---

## 6. Phase 2 완료 기준 달성 현황

| 항목 | 상태 |
|------|------|
| CLIP zero-shot 파이프라인 (`src/clip_scorer.py`) | ✅ |
| 쿼리 목록 (`config/clip_queries.yaml`) | ✅ |
| 파일럿 10건 실험 → clip_score 분포 확인 | ✅ |
| threshold 최적화 (0.22→0.27) | ✅ |
| `vod_clip_concept.parquet` 생성 | ✅ (6,996건) |
| `tests/test_phase2_clip.py` PASS | ✅ (13/13) |
| `docs/reports/phase2_clip_report.md` | ✅ (본 문서) |

---

## 7. Phase 3 계획

**목적**: 영상만으로 불가한 지역성·맥락을 DB 메타데이터로 보완

```
DB vod 테이블 (asset_nm, genre, smry)
    → 지역 키워드 추출 → region_hint
    → 장르 매핑 → scene_hint
    → vod_detected_object.parquet에 병합
```

산출물 추가 컬럼:

| 컬럼 | 타입 | 예시 |
|------|------|------|
| `region_hint` | str | "강원도", "제주도" |
| `scene_hint` | str | "여행", "요리", "토크" |

---

## 8. 산출물

| 파일 | 위치 | 크기 |
|------|------|------|
| `vod_clip_concept.parquet` | `Object_Detection/data/` | 6,996건 |
| `clip_status.json` | `Object_Detection/data/` | 10건 처리 기록 |
| `clip_score.log` | `Object_Detection/data/` | 실행 로그 |
