# PLAN_01: 인기 VOD 집계 및 추천 결과 생성

**브랜치**: Normal_Recommendation
**스크립트**: `scripts/run_pipeline.py`
**라이브러리**: `src/popularity.py`, `src/db.py`
**입력**: `public.vod` 테이블
**출력**: `data/recommendations_popular_YYYYMMDD.parquet`

---

## 목표

1. `vod` 테이블에서 `rating`, `release_date`, `series_nm` 로드
2. `series_nm` 기준으로 시리즈 단위 집약
3. rating + 최신성(release_date) 기반 인기 점수 계산
4. 고정 4개 장르(영화/드라마/예능/애니) 각 Top-20 추출
5. 결과를 parquet으로 저장

---

## 파이프라인 상세

### Step 1: vod 테이블 로드

```sql
SELECT full_asset_id, genre, ct_cl, rating, release_date, series_nm
FROM public.vod;
```

### Step 2: 시리즈 집약 (`aggregate_by_series`)

- `series_nm` NULL → 개별 VOD 그대로 처리
- `series_nm` 있음 → 시리즈 단위 1개로 집약
  - `rating`: 에피소드 평균값
  - `release_date`: 가장 최신 에피소드 기준

### Step 3: 인기 점수 계산 (`calc_popularity_score`)

```python
# 최신성: 오늘 기준 경과 일수 → 역수 정규화 (최신=1, 오래됨=0)
norm_recency = 1 - minmax_norm(days_from_today)

score = 0.6 * norm(rating) + 0.4 * norm_recency
```

| 파라미터 | 값 | 설명 |
|---------|---|------|
| `rating_weight` | 0.6 | rating 가중치 |
| `recency_weight` | 0.4 | 최신성 가중치 |
| `release_date` NULL | 0으로 처리 | 미수집 VOD |

### Step 4: 장르별 Top-20 추출 (`get_top_n_by_genre`)

- 슬래시(`/`) 구분 다중 장르 → explode
- **고정 4개 장르만 필터**: 영화 / 드라마 / 예능 / 애니
- 장르별 score 내림차순 Top-20

---

## 설정값 (`config/recommend_config.yaml`)

```yaml
popularity:
  rating_weight: 0.6
  recency_weight: 0.4
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
