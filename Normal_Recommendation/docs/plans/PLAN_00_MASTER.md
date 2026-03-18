# PLAN_00: Normal Recommendation 파이프라인 마스터 플랜

**브랜치**: Normal_Recommendation
**담당**: 담당자 C (Cold Start 대응)
**작성일**: 2026-03-17
**최종수정**: 2026-03-18 (POPULARITY_SCORE_DESIGN.md v2 반영)
**목표**: 시청 이력 없는 신규 유저(Cold Start) 대상으로 장르별 인기 VOD Top-20을 생성하여 `serving.popular_recommendation` 테이블에 적재

---

## 전체 구조

```
[PLAN_01] vod 테이블 로드 (tmdb_vote_average, tmdb_vote_count, release_date, series_nm)
          watch_history 시청 통계 집계 (watch_count, watch_count_7d, completion_rate, satisfaction)
             → series_nm 기준 시리즈 집약
             → 2단계 인기 점수 계산 (cold/warm/blend)
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
| PLAN_01 | `scripts/run_pipeline.py` | `public.vod` + `public.watch_history` | `data/recommendations_popular_YYYYMMDD.parquet` | 수 분 |
| PLAN_02 | `scripts/export_to_db.py` | parquet 파일 | `serving.popular_recommendation` | 수 분 |

---

## 인기 지표 계산 방식 (2단계 전략)

### 개요

시청 이력 유무에 따라 공식을 분리하고 선형 보간(blend)으로 전환.

```
watch_count < WARM_THRESHOLD(10) → cold stage (TMDB 기반)
watch_count >= WARM_THRESHOLD    → warm stage (자체 시청 기반)
그 사이                          → blend (선형 보간)
```

### Cold Stage 공식

```
score_cold = 0.65 * vote_score + 0.35 * freshness
```

### Warm Stage 공식

```
score_warm = 0.45 * watch_heat + 0.25 * quality + 0.15 * vote_score + 0.15 * freshness
```

### 컴포넌트 설명

| 컴포넌트 | 설명 |
|---------|------|
| `vote_score` | TMDB 평점 × 로그 정규화 × VC credibility 댐핑 |
| `freshness` | 출시일부터 1년간 1.0→0.0 선형 감쇄 |
| `watch_heat` | 최근 7일 시청 수 / 전체 평균 (상한 5배, 정규화) |
| `quality` | avg(completion_rate) × avg(satisfaction), 시청 5건 미만 시 0 |

### 확정 파라미터

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `WARM_THRESHOLD` | 10 | warm stage 전환 시청 수 기준 |
| `QUALITY_MIN_WC` | 5 | quality 계산 최소 시청 수 |
| `VC_CREDIBILITY_CAP` | 50 | vote_count 신뢰도 댐핑 상한 |
| `top_n` | 20 | 장르별 추천 개수 |

### 시리즈 집약 기준

- `series_nm` 기준으로 그룹핑 — 동일 시리즈는 **1개**만 추천
- `series_nm` NULL → 단편/독립작품, 개별 VOD 그대로 처리
- tmdb_vote_average: 시리즈 내 에피소드 **평균**
- tmdb_vote_count: 시리즈 내 에피소드 **합산**
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

## ⚠️ 전제 조건 (실행 전 필수)

1. **Database_Design 마이그레이션 완료** — `vod` 테이블에 `tmdb_vote_average`, `tmdb_vote_count`, `tmdb_popularity` 컬럼 추가 필요
2. **RAG 파이프라인 수정 완료** — TMDB API 응답에서 3개 필드 수집 후 vod 테이블 적재 필요

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
│   └── recommend_config.yaml   ← warm_threshold, quality_min_wc, 가중치, top_n
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
| vod 테이블 | 166,159건 (`full_asset_id`, `genre`, `ct_cl`, `tmdb_vote_average`, `tmdb_vote_count`, `release_date`, `series_nm`) |
| watch_history 테이블 | `vod_id_fk`, `strt_dt`, `completion_rate`, `satisfaction` |
| 대상 장르 | 영화 / 드라마 / 예능 / 애니 고정 4개 |
| 추천 대상 유저 | Cold Start 유저 (시청 이력 없음) |
| recommendation_type | `'POPULAR'` 고정값 |
| expires_at | 현재시간 + 7일 (TTL) |
| UNIQUE constraint | `serving.popular_recommendation` UNIQUE (genre, rank) |
| 업데이트 주기 | 1주일 1회 수동 실행 |

---

## 진행 체크리스트

### 전제 조건
- [ ] Database_Design: vod 테이블에 `tmdb_vote_average`, `tmdb_vote_count` 컬럼 추가
- [ ] RAG: TMDB API 3개 필드 수집 후 vod 테이블 적재

### PLAN_01: 인기 VOD 집계 및 추천 결과 생성
- [x] `src/popularity.py` 구현 (2단계 cold/warm/blend 인기 점수 계산)
- [x] `src/db.py` 구현 (DB 연결 + load_watch_stats)
- [x] `config/recommend_config.yaml` 작성 (warm_threshold, 가중치, top_n)
- [x] `scripts/run_pipeline.py` 구현 (실행 스크립트)
- [ ] 전제 조건 완료 후 parquet 저장 확인

### PLAN_02: DB 적재
- [x] `scripts/export_to_db.py` 구현
- [ ] 조장에게 parquet 전달
- [ ] `serving.popular_recommendation` 적재 완료 확인

### 테스트
- [x] `tests/test_popularity.py` 작성 (pytest 33개)
- [x] 단위 테스트 전체 통과 확인

---

**다음**: PLAN_01_POPULARITY.md
