# PLAN_00: Normal Recommendation 파이프라인 마스터 플랜

**브랜치**: Normal_Recommendation
**담당**: 담당자 C (Cold Start 대응)
**작성일**: 2026-03-17
**목표**: 시청 이력 없는 신규 유저(Cold Start) 대상으로 장르별 인기 VOD Top-20을 생성하여 `serving.popular_recommendation` 테이블에 적재

---

## 전체 구조

```
[PLAN_01] vod 테이블 로드 (rating, release_date, series_nm)
             → series_nm 기준 시리즈 집약
             → rating(0.6) + 최신성(0.4) 인기 점수 계산
             → 고정 4개 장르(영화/드라마/예능/애니) 각 Top-20 추출
             → data/recommendations_popular_YYYYMMDD.parquet 저장
                             ↓
[PLAN_02] parquet → serving.popular_recommendation 적재
                   (조장 전용: DB 쓰기 권한 필요)
```

---

## 단계별 요약

| 단계 | 파일 | 입력 | 출력 | 예상 시간 |
|------|------|------|------|---------|
| PLAN_01 | `scripts/run_pipeline.py` | `public.vod` 테이블 | `data/recommendations_popular_YYYYMMDD.parquet` | 수 분 |
| PLAN_02 | `scripts/export_to_db.py` | parquet 파일 | `serving.popular_recommendation` | 수 분 |

---

## 인기 지표 계산 방식

### 인기 점수 공식

```
score = 0.6 * norm(rating) + 0.4 * recency_score(release_date)
```

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `rating_weight` | 0.6 | rating 가중치 |
| `recency_weight` | 0.4 | 최신성 가중치 |
| `top_n` | 20 | 장르별 추천 개수 |

- **정규화**: min-max 정규화 (0~1 범위)
- **rating NULL 처리**: 0으로 대체 후 정규화
- **release_date NULL 처리**: recency 0으로 처리 (최하위 취급)
- **장르 분리**: 슬래시(`/`) 구분 다중 장르 → 각 장르에 개별 등록

### 시리즈 집약 기준

- `series_nm` 기준으로 그룹핑 — 동일 시리즈는 **1개**만 추천
- `series_nm` NULL → 단편/독립작품, 개별 VOD 그대로 처리
- rating: 시리즈 내 에피소드 **평균**
- release_date: 시리즈 내 **가장 최신** 에피소드 기준

---

## ⚠️ DB 쓰기 권한 분리

### 배경
- **팀원**: DB 읽기 권한만 보유 → parquet 파일로 저장 후 조장에게 전달
- **조장 (dhwang0803)**: DB 쓰기 권한 보유 → parquet 받아서 DB 최종 적재

### `scripts/run_pipeline.py` 실행 방법

```bash
# 팀원 (parquet 저장)
python Normal_Recommendation/scripts/run_pipeline.py --output parquet

# 드라이런
python Normal_Recommendation/scripts/run_pipeline.py --dry-run

# 조장 (DB 직접 적재)
python Normal_Recommendation/scripts/run_pipeline.py
```

### Parquet 스키마

```python
# data/recommendations_popular_YYYYMMDD.parquet
# 컬럼: category_value, rank, vod_id_fk, score, recommendation_type
# 타입: str,            int,  str,        float, str
```

---

## 파일 구조

```
Normal_Recommendation/
├── src/
│   ├── popularity.py           ← PLAN_01: 인기 VOD 집계 로직 (import 전용)
│   └── db.py                   ← DB 연결 공통 모듈 (import 전용)
├── scripts/
│   ├── run_pipeline.py         ← PLAN_01: 추천 결과 생성 실행
│   └── export_to_db.py         ← PLAN_02: 추천 결과 DB 적재 (조장 전용)
├── tests/
│   └── test_popularity.py      ← pytest
├── config/
│   └── recommend_config.yaml   ← rating_weight, recency_weight, top_n
└── docs/
    ├── plans/
    │   ├── PLAN_00_MASTER.md   ← 이 파일
    │   ├── PLAN_01_POPULARITY.md
    │   └── PLAN_02_EXPORT_DB.md
    └── reports/                ← 실험 리포트
```

---

## 핵심 제약 및 전제

| 항목 | 내용 |
|------|------|
| vod 테이블 | 166,159건 (`full_asset_id`, `genre`, `ct_cl`, `rating`, `release_date`, `series_nm`) |
| 대상 장르 | 영화 / 드라마 / 예능 / 애니 고정 4개 |
| 추천 대상 유저 | Cold Start 유저 (시청 이력 없음) |
| recommendation_type | `'POPULAR'` 고정값 |
| expires_at | 현재시간 + 7일 (TTL) |
| UNIQUE constraint | `serving.popular_recommendation` UNIQUE (genre, rank) |
| 업데이트 주기 | 1주일 1회 수동 실행 |

---

## 진행 체크리스트

### PLAN_01: 인기 VOD 집계 및 추천 결과 생성
- [x] `src/popularity.py` 구현 (인기 지표 계산 로직)
- [x] `src/db.py` 구현 (DB 연결 공통 모듈)
- [x] `config/recommend_config.yaml` 작성 (rating_weight, recency_weight, top_n)
- [x] `scripts/run_pipeline.py` 구현 (실행 스크립트)
- [ ] parquet 저장 확인

### PLAN_02: DB 적재
- [x] `scripts/export_to_db.py` 구현
- [ ] 조장에게 parquet 전달
- [ ] `serving.popular_recommendation` 적재 완료 확인

### 테스트
- [x] `tests/test_popularity.py` 작성 (pytest 22개)
- [x] 단위 테스트 전체 통과 확인

---

**다음**: PLAN_01_POPULARITY.md
