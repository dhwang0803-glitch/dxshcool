# PLAN_01: 인기 VOD 집계 및 추천 결과 생성

**브랜치**: Normal_Recommendation
**스크립트**: `scripts/run_pipeline.py`
**라이브러리**: `src/popularity.py`, `src/db.py`
**입력**: `public.vod` 테이블 + `public.watch_history` 테이블
**출력**: `data/recommendations_popular_YYYYMMDD.parquet`
**최종수정**: 2026-03-18 (POPULARITY_SCORE_DESIGN.md v2 반영)

---

## 목표

1. `vod` 테이블에서 `tmdb_vote_average`, `tmdb_vote_count`, `release_date`, `series_nm` 로드
2. `watch_history` 테이블에서 VOD별 시청 통계 집계
3. `series_nm` 기준으로 시리즈 단위 집약
4. 2단계 cold/warm/blend 인기 점수 계산
5. 고정 4개 장르(영화/드라마/예능/애니) 각 Top-20 추출
6. 결과를 parquet으로 저장

---

## 파이프라인 상세

### Step 1: vod 테이블 로드

```sql
SELECT full_asset_id, genre, ct_cl, release_date, series_nm,
       tmdb_vote_average, tmdb_vote_count
FROM public.vod;
```

### Step 2: watch_history 시청 통계 집계

```sql
SELECT
    vod_id_fk,
    COUNT(*)                                                         AS watch_count,
    COUNT(*) FILTER (WHERE strt_dt >= NOW() - INTERVAL '7 days')    AS watch_count_7d,
    AVG(completion_rate)                                             AS avg_completion_rate,
    AVG(satisfaction)                                                AS avg_satisfaction
FROM public.watch_history
GROUP BY vod_id_fk;
```

### Step 3: 시리즈 집약 (`aggregate_by_series`)

- `series_nm` NULL → 개별 VOD 그대로 처리
- `series_nm` 있음 → 시리즈 단위 1개로 집약
  - `tmdb_vote_average`: 에피소드 **평균**
  - `tmdb_vote_count`: 에피소드 **합산**
  - `release_date`: 가장 최신 에피소드 기준

### Step 4: 인기 점수 계산 (`calc_popularity_score`)

#### 컴포넌트 함수

**`calc_vote_score(df, vc_credibility_cap=50)`**
```python
vc_weight = np.minimum(df["tmdb_vote_count"], vc_credibility_cap) / vc_credibility_cap
log_norm  = np.log1p(df["tmdb_vote_average"]) / np.log1p(10)
vote_score = (log_norm * vc_weight).fillna(0).clip(0, 1)
```

**`calc_freshness(df)`**
```python
days_old  = (today - df["release_date"]).dt.days.fillna(366)
freshness = (1 - days_old / 365).clip(0, 1)
```

**`calc_watch_heat(df, watch_stats)`**
```python
heat_cap  = watch_count_7d_mean * 5
raw_heat  = watch_count_7d.clip(upper=heat_cap) / heat_cap
watch_heat = raw_heat.fillna(0).clip(0, 1)
```

**`calc_quality(df, watch_stats, quality_min_wc=5)`**
```python
quality = avg_completion_rate * avg_satisfaction  # watch_count < quality_min_wc → 0
```

#### 2단계 점수 계산

```python
score_cold = 0.65 * vote_score + 0.35 * freshness
score_warm = 0.45 * watch_heat + 0.25 * quality + 0.15 * vote_score + 0.15 * freshness
blend      = (watch_count / WARM_THRESHOLD).clip(0, 1)
score      = (1 - blend) * score_cold + blend * score_warm
```

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `WARM_THRESHOLD` | 10 | warm stage 전환 시청 수 기준 |
| `QUALITY_MIN_WC` | 5 | quality 계산 최소 시청 수 |
| `VC_CREDIBILITY_CAP` | 50 | vote_count 신뢰도 댐핑 상한 |

### Step 5: 장르별 Top-20 추출 (`get_top_n_by_genre`)

- 슬래시(`/`) 구분 다중 장르 → explode
- **고정 4개 장르만 필터**: 영화 / 드라마 / 예능 / 애니
- 장르별 score 내림차순 Top-20

---

## 설정값 (`config/recommend_config.yaml`)

```yaml
popularity:
  warm_threshold: 10
  quality_min_wc: 5
  vc_credibility_cap: 50
  cold_vote_weight: 0.65
  cold_freshness_weight: 0.35
  warm_watch_heat_weight: 0.45
  warm_quality_weight: 0.25
  warm_vote_weight: 0.15
  warm_freshness_weight: 0.15
  top_n: 20

export:
  recommendation_type: "POPULAR"
  ttl_days: 7
  output_dir: "Normal_Recommendation/data"
```

---

## Parquet 출력 스키마

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `category_value` | str | 장르명 (영화/드라마/예능/애니) |
| `rank` | int | 장르 내 순위 (1~20) |
| `vod_id_fk` | str | VOD ID |
| `score` | float | 인기 점수 (0~1) |
| `recommendation_type` | str | 고정값: `'POPULAR'` |

---

## 실행 방법

```bash
# 팀원 (parquet 저장)
python Normal_Recommendation/scripts/run_pipeline.py --output parquet

# 드라이런
python Normal_Recommendation/scripts/run_pipeline.py --dry-run

# 조장 (DB 직접 적재)
python Normal_Recommendation/scripts/run_pipeline.py
```

---

**다음**: PLAN_02_EXPORT_DB.md
