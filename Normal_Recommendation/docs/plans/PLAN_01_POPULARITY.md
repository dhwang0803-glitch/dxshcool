# PLAN_01: 인기 VOD 집계 및 추천 결과 생성

**브랜치**: Normal_Recommendation
**스크립트**: `scripts/run_pipeline.py`
**라이브러리**: `src/popularity.py`, `src/db.py`
**입력**: `public.vod` + `public.watch_history` 테이블
**출력**: `data/recommendations_popular_YYYYMMDD.parquet`

---

## 목표

1. `watch_history`에서 VOD별 시청 건수(조회수) 집계
2. `vod` 테이블의 `rating`과 결합하여 인기 점수 계산
3. 장르(`genre`) 및 콘텐츠 유형(`ct_cl`)별 Top-N VOD 추출
4. 결과를 parquet으로 저장

---

## 인기 점수 계산 상세

### Step 1: 조회수 집계

```sql
SELECT vod_id_fk, COUNT(*) AS watch_count
FROM public.watch_history
GROUP BY vod_id_fk;
```

### Step 2: vod 테이블과 조인

```sql
SELECT
    v.full_asset_id,
    v.genre,
    v.ct_cl,
    v.rating,
    COALESCE(w.watch_count, 0) AS watch_count
FROM public.vod v
LEFT JOIN (
    SELECT vod_id_fk, COUNT(*) AS watch_count
    FROM public.watch_history
    GROUP BY vod_id_fk
) w ON v.full_asset_id = w.vod_id_fk;
```

### Step 3: 인기 점수 계산

```python
# min-max 정규화
def minmax_norm(series):
    mn, mx = series.min(), series.max()
    if mx == mn:
        return series * 0
    return (series - mn) / (mx - mn)

df['norm_watch'] = minmax_norm(df['watch_count'])
df['norm_rating'] = minmax_norm(df['rating'].fillna(0))

# 가중합 (config에서 로드)
df['score'] = w1 * df['norm_watch'] + w2 * df['norm_rating']
```

### Step 4: 장르별 Top-N 추출

```python
# 슬래시 구분 다중 장르 처리
df_exploded = df.assign(genre=df['genre'].str.split('/')).explode('genre')
df_exploded['genre'] = df_exploded['genre'].str.strip()

# 장르별 Top-N
genre_top = (
    df_exploded
    .sort_values('score', ascending=False)
    .groupby('genre')
    .head(top_n)
    .assign(rank=lambda x: x.groupby('genre').cumcount() + 1)
)
```

### Step 5: ct_cl별 Top-N 추출

```python
ctcl_top = (
    df.sort_values('score', ascending=False)
    .groupby('ct_cl')
    .head(top_n)
    .assign(rank=lambda x: x.groupby('ct_cl').cumcount() + 1)
)
```

---

## 설정값 (`config/recommend_config.yaml`)

```yaml
popularity:
  watch_weight: 0.7    # w1: 조회수 가중치
  rating_weight: 0.3   # w2: 평점 가중치
  top_n: 20            # 카테고리별 추천 개수

export:
  recommendation_type: "POPULAR"
  output_dir: "data"
```

---

## Parquet 출력 스키마

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id_fk` | str | VOD ID (`full_asset_id`) |
| `rank` | int | 카테고리 내 순위 (1~top_n) |
| `score` | float | 인기 점수 (0~1) |
| `recommendation_type` | str | 고정값: `'POPULAR'` |
| `genre` | str | 해당 장르 (explode 적용) |
| `ct_cl` | str | 콘텐츠 유형 |

---

## 실행 방법

```bash
conda activate myenv

# 팀원 (parquet 저장)
python scripts/run_pipeline.py --output parquet

# 드라이런 (저장 없이 결과만 출력)
python scripts/run_pipeline.py --dry-run

# 조장 (DB 직접 적재)
python scripts/run_pipeline.py
```

---

## 예상 산출물

```
Normal_Recommendation/data/
└── recommendations_popular_20260317.parquet
    ← 장르별 Top-20 + ct_cl별 Top-20 통합
    ← 예상 행 수: 장르 수 × 20 + ct_cl 수 × 20
```

---

**다음**: PLAN_02_EXPORT_DB.md
