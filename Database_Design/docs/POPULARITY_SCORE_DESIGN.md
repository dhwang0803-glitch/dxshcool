# 인기도 스코어 설계 (Popularity Score Design)

**작성일**: 2026-03-18
**상태**: 설계 검토 중
**관련 브랜치**: `Database_Design`, `gen_sentence`, `CF_Engine`, `Vector_Search`
**목적**: `serving.popular_recommendation`의 TRENDING/POPULAR 스코어 산출 공식 및 DB 컬럼 설계

---

## 1. 배경

### 해결해야 할 문제

`serving.popular_recommendation` 테이블에 장르별 Top-N 인기 추천을 적재하려면
**인기도(score)를 정량화하는 공식**이 필요하다.

인기도는 두 가지 요소를 반영해야 한다:
- **화제성** — 얼마나 많이, 최근에 시청/평가되고 있는가
- **최신성** — 최근 출시된 콘텐츠에 가산점

### 데이터 시점 문제

| 구분 | 기존 VOD (2023) | 신규 VOD (2025~) |
|------|---------------|-----------------|
| watch_history | 있음 (399만건) | **없음** (시청 이력 0) |
| TMDB vote_average | 있음 | 있음 |
| TMDB vote_count | 있음 (누적 높음) | 있음 (초기에는 낮음) |
| TMDB popularity | 있음 (2023 기준과 현재 괴리) | 있음 (현재 기준) |
| release_date | 2023 이전 | 2025~ |

신규 VOD는 자체 시청 시그널이 0이므로, 단일 공식으로는 공정한 인기도 산출이 불가능하다.

### TMDB popularity 왜곡 문제

TMDB `popularity`는 최근 7일 기준 조회수·검색량·소셜 언급·찜 등을 종합한 점수이다.
직접 사용하기에는 왜곡이 크다:

| 왜곡 유형 | 예시 | 원인 |
|----------|------|------|
| 장수 예능 과대평가 | 무한도전 195 vs 기생충 25 | 시즌/회차 반복 조회로 누적 부풀림 |
| 해외 인기 편향 | 한국 비인기작인데 해외에서 화제 | TMDB는 글로벌 플랫폼 |
| 플랫폼 출시 효과 | 넷플릭스 공개 직후 급등 | IPTV 시청 패턴과 무관한 스파이크 |

**결론: `popularity`는 인기도 공식에 직접 사용하지 않는다.**
`vote_average`와 `vote_count`만 외부 평판 시그널로 활용한다.

---

## 2. Cold Start 2단계 전략

시청 데이터 유무에 따라 인기도 산출 공식을 2단계로 분리한다.

```
                    시청 이력 누적
                         │
    ┌────────────────────┼────────────────────┐
    │   Stage 1          │   Stage 2          │
    │   Cold Start       │   Warm             │
    │   (시청 < 임계치)    │   (시청 >= 임계치)   │
    │                    │                    │
    │   TMDB 기반 공식    │   자체 시청 기반     │
    └────────────────────┴────────────────────┘
```

---

## 3. 인기도 공식

### 공통 컴포넌트

#### vote_score (외부 평판)

```
vote_score = (vote_average / 10) × log(vote_count + 1) / log(max_vote_count + 1)
```

- `vote_average / 10` : 10점 만점을 0~1 스케일로 정규화
- `log(vote_count + 1) / log(max_vote_count + 1)` : 평가자 수 로그 정규화
  - 20명짜리 7.7점 vs 2만명짜리 8.5점의 **신뢰도 차이** 반영
  - log 스케일로 극단적 차이 완화
- `max_vote_count` : 전체 VOD 중 최대 vote_count (정규화 기준)

#### freshness (최신성 감쇄)

```
freshness = max(0, 1 - (today - release_date).days / 365)
```

- 출시일부터 1년간 1.0 → 0.0 **선형 감쇄**
- 1년 이상 경과 시 0 (최신성 보너스 없음)
- `release_date`가 NULL이면 freshness = 0

### Stage 1: Cold Start (시청 이력 부족)

TMDB 데이터만으로 인기도를 산출한다.

```
score_cold = 0.65 × vote_score + 0.35 × freshness
```

| 컴포넌트 | 가중치 | 근거 |
|---------|--------|------|
| vote_score | 0.65 | 시청 데이터 없으므로 외부 평판이 핵심 |
| freshness | 0.35 | 최신 콘텐츠 노출 기회 보장 |

**TMDB popularity는 사용하지 않음** — 왜곡 원인 제거.

### Stage 2: Warm (시청 이력 충분)

자체 시청 데이터 중심으로 산출한다.

```
score_warm = 0.45 × watch_heat + 0.25 × quality + 0.15 × vote_score + 0.15 × freshness
```

#### watch_heat (자체 인기)

```
watch_heat = 최근 7일 시청 수 / 전체 VOD 평균 시청 수
```

- 1.0 = 평균적 인기, 2.0 = 평균 2배 인기
- min(watch_heat, 5.0)으로 상한 클램핑 (이상치 방지)
- 정규화: `watch_heat / 5.0` → 0~1 스케일

#### quality (자체 품질)

```
quality = avg(completion_rate) × avg(satisfaction)
```

- completion_rate: 0~1 (완주율)
- satisfaction: 0~1 (베이지안 만족도)
- 둘의 곱: 완주하면서 만족한 콘텐츠가 높은 점수

### 가중치 비교표

| 컴포넌트 | Stage 1 (cold) | Stage 2 (warm) | 역할 |
|---------|---------------|----------------|------|
| watch_heat (자체 인기) | 0 | **0.45** | 우리 플랫폼 실제 인기 |
| quality (자체 품질) | 0 | **0.25** | 완주율 × 만족도 |
| vote_score (외부 평판) | **0.65** | 0.15 | TMDB 평점 (신뢰도 보정) |
| freshness (최신성) | **0.35** | 0.15 | 출시 1년 이내 가산 |

### 전환 로직 (선형 보간)

```python
WARM_THRESHOLD = 30  # 시청 이력 30건 이상이면 Stage 2

if watch_count >= WARM_THRESHOLD:
    score = score_warm
else:
    blend = watch_count / WARM_THRESHOLD  # 0.0 ~ 1.0
    score = (1 - blend) * score_cold + blend * score_warm
```

- 30건 미만: cold↔warm **선형 보간** → 급격한 점수 변동 방지
- 30건 이상: 완전 warm 전환
- 기존 2023 VOD: watch_history 충분 → **처음부터 Stage 2**

---

## 4. 적용 대상

### POPULAR vs TRENDING

`serving.popular_recommendation.recommendation_type` 에 따라 공식 변형:

| 타입 | 공식 변형 | 설명 |
|------|---------|------|
| `POPULAR` | 위 공식 그대로 | 종합 인기도 |
| `TRENDING` | watch_heat를 **7일 증가율**로 교체 | 급상승 감지 |

#### TRENDING용 watch_heat 변형

```
trending_heat = (최근 7일 시청 수 - 이전 7일 시청 수) / (이전 7일 시청 수 + 1)
```

- 양수: 시청 증가 (급상승)
- 0 이하: 정체 또는 하락 → TRENDING 후보에서 제외
- Cold Start VOD: trending_heat = 0 (시청 이력 없으므로 TRENDING 대상 아님)

---

## 5. DB 컬럼 설계

### 5-1. `public.vod` 테이블 — TMDB 평점 컬럼 추가

기존 `vod` 테이블에 TMDB 평점 정보를 저장할 컬럼 3개를 추가한다.

| 컬럼 | 타입 | 비고 |
|------|------|------|
| `tmdb_vote_average` | REAL | TMDB 평점 (0.0~10.0) |
| `tmdb_vote_count` | INTEGER | TMDB 평가 참여자 수 |
| `tmdb_popularity` | REAL | TMDB 인기도 점수 (참고용, 공식에 미사용) |

#### 마이그레이션 SQL

```sql
-- migrations/YYYYMMDD_add_tmdb_rating_to_vod.sql

BEGIN;

ALTER TABLE vod
    ADD COLUMN IF NOT EXISTS tmdb_vote_average REAL,
    ADD COLUMN IF NOT EXISTS tmdb_vote_count   INTEGER,
    ADD COLUMN IF NOT EXISTS tmdb_popularity   REAL;

COMMENT ON COLUMN vod.tmdb_vote_average IS 'TMDB 평점 (0.0~10.0). RAG 파이프라인이 수집.';
COMMENT ON COLUMN vod.tmdb_vote_count   IS 'TMDB 평가 참여자 수. vote_score 산출에 사용.';
COMMENT ON COLUMN vod.tmdb_popularity   IS 'TMDB 인기도 점수. 참고용 저장, 인기도 공식에는 미사용 (왜곡 우려).';

COMMIT;
```

#### 왜 `tmdb_popularity`도 저장하는가?

인기도 공식에 직접 사용하지 않지만, 추후 분석·비교 목적으로 원본 데이터를 보존한다.
분석 후 공식 재조정 시 활용 가능.

### 5-2. 수집 방식

기존 RAG 파이프라인(`RAG/src/meta_sources.py`)의 `_fetch_series_data()`에서
TMDB detail API 응답을 이미 받고 있다. 현재 무시하는 3개 필드를 추가 추출하면 된다:

```python
# meta_sources.py _fetch_series_data() 내부
# 기존: director, cast_lead, rating, release_date, smry 추출
# 추가:
result["tmdb_vote_average"] = detail.get("vote_average")
result["tmdb_vote_count"]   = detail.get("vote_count")
result["tmdb_popularity"]   = detail.get("popularity")
```

**새로운 API 호출 없이** 기존 호출 응답에서 추출 가능.

### 5-3. 기존 VOD 일괄 수집

2023 기존 VOD 166,159건에 대해 TMDB 평점을 일괄 수집해야 한다.
RAG 파이프라인의 `tmdb_id`가 이미 매칭된 VOD는 detail API 1회 호출로 수집 가능.

```
수집 대상: tmdb_vote_average IS NULL인 VOD
수집 방법: RAG 파이프라인 재실행 또는 별도 스크립트
예상 소요: 166K건 × TMDB rate limit(40 req/s) ≈ ~70분
```

### 5-4. TMDB API 필드 검증 결과

실제 API 호출로 확인한 데이터 (2026-03-18):

| VOD | vote_average | vote_count | popularity | 비고 |
|-----|-------------|------------|------------|------|
| 기생충 (영화) | 8.493 | 20,282 | 25.90 | 고평가 + 고신뢰도 |
| 범죄도시4 (영화) | 7.169 | 228 | 4.56 | 중평가 + 중신뢰도 |
| 무한도전 (TV) | 7.7 | 20 | 195.02 | popularity 왜곡 사례 |

- `search/multi`와 `movie/{id}`, `tv/{id}` detail 양쪽에서 정상 반환
- 인증: `api_key` 파라미터 방식 사용 (Bearer token은 detail에서 401 발생)

---

## 6. 인기도 산출 데이터 플로우

```
[데이터 수집]

  RAG 파이프라인 (기존 + 추가 추출)
    → vod.tmdb_vote_average
    → vod.tmdb_vote_count
    → vod.tmdb_popularity

  watch_history (기존 데이터)
    → 최근 7일 시청 수, 완주율, 만족도

        │
        ▼

[인기도 산출] (배치 스크립트, 주 1회)

  1) 전체 VOD에 대해 watch_count 집계
  2) VOD별 Stage 판별 (cold / warm / blend)
  3) 컴포넌트 계산:
     - vote_score ← tmdb_vote_average, tmdb_vote_count
     - freshness  ← release_date
     - watch_heat ← watch_history (최근 7일)
     - quality    ← completion_rate, satisfaction
  4) 가중합 → 최종 score (0.0~1.0)
  5) 장르별 Top-N 정렬

        │
        ▼

[적재]

  serving.popular_recommendation
    genre, rank, vod_id_fk, score,
    recommendation_type = 'POPULAR' | 'TRENDING'

        │
        ▼

[서빙]

  API_Server → Frontend
    "영화 Top-20", "이번 주 급상승 드라마"
```

---

## 7. 산출 예시

### Case 1: 기생충 (기존 VOD, Stage 2)

```
watch_count = 1,200 (>= 30 → Stage 2)

vote_score  = (8.493/10) × log(20283) / log(20283) = 0.849
freshness   = max(0, 1 - (1095/365)) = 0  (2023 출시, 3년 경과)
watch_heat  = 1200 / avg(500) = 2.4 → 2.4/5.0 = 0.48
quality     = 0.82 × 0.78 = 0.64

score_warm  = 0.45×0.48 + 0.25×0.64 + 0.15×0.849 + 0.15×0
            = 0.216 + 0.160 + 0.127 + 0
            = 0.503
```

### Case 2: 신작 영화 X (신규 VOD, Stage 1)

```
watch_count = 0 (< 30 → Stage 1)

vote_score  = (7.5/10) × log(151) / log(20283) = 0.75 × 0.506 = 0.380
freshness   = max(0, 1 - (30/365)) = 0.918  (출시 30일)

score_cold  = 0.65×0.380 + 0.35×0.918
            = 0.247 + 0.321
            = 0.568
```

### Case 3: 신작 영화 X (시청 15건 쌓인 후, 보간)

```
watch_count = 15 (< 30 → blend)
blend       = 15/30 = 0.5

score_cold  = 0.568 (위와 동일)
score_warm  = 0.45×(15/avg/5) + 0.25×quality + 0.15×0.380 + 0.15×0.918
            = (계산 생략) ≈ 0.490

score       = 0.5 × 0.568 + 0.5 × 0.490
            = 0.529
```

---

## 8. 향후 작업

| 순서 | 작업 | 브랜치 | 비고 |
|------|------|--------|------|
| 1 | vod 테이블 마이그레이션 (tmdb_vote_* 3개 컬럼) | `Database_Design` | 마이그레이션 SQL 작성 + VPC 실행 |
| 2 | RAG 파이프라인에 3개 필드 추출 추가 | `RAG` | meta_sources.py 수정 |
| 3 | 기존 VOD 일괄 TMDB 평점 수집 스크립트 | `RAG` 또는 별도 | 166K건 일괄 수집 |
| 4 | 인기도 산출 배치 스크립트 구현 | `CF_Engine` 또는 `gen_sentence` | 주 1회 실행 |
| 5 | popular_recommendation 적재 파이프라인 | 동일 | DELETE + INSERT (장르 단위) |
| 6 | API 엔드포인트 구현 | `API_Server` | `GET /recommend/popular?genre=영화` |

---

## 9. 가중치 튜닝 가이드

초기 가중치는 경험적 추정이다. 실 데이터 적재 후 아래 방법으로 조정한다:

1. **정성 평가**: 장르별 Top-20 결과를 사람이 보고 "이상한 순위" 식별
2. **A/B 테스트**: 가중치 조합 2~3개를 비교 (CTR, 체류 시간)
3. **격자 탐색**: α, β, γ, δ 를 0.05 단위로 변경하며 nDCG 등 랭킹 메트릭 측정

가중치 변경 시 이 문서를 업데이트한다.
