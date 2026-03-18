# 인기도 스코어 설계 (Popularity Score Design)

**작성일**: 2026-03-18
**상태**: v2 파라미터 확정 (100건 실데이터 검증 완료)
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
vc_credibility = min(vote_count, VC_CREDIBILITY_CAP) / VC_CREDIBILITY_CAP
vote_score = (vote_average / 10) × log(vote_count + 1) / log(max_vote_count + 1) × vc_credibility
```

- `vote_average / 10` : 10점 만점을 0~1 스케일로 정규화
- `log(vote_count + 1) / log(max_vote_count + 1)` : 평가자 수 로그 정규화
  - 20명짜리 7.7점 vs 2만명짜리 8.5점의 **신뢰도 차이** 반영
  - log 스케일로 극단적 차이 완화
- `vc_credibility` : 평가 참여자 수 신뢰도 댐핑 (v2 추가)
  - `VC_CREDIBILITY_CAP = 50` — 50명 미만 평가 시 vote_score를 비례 감쇄
  - VA=10.0/VC=1 같은 **소수 고평가 과대평가** 방지
  - 예: VC=1 → 0.02배, VC=10 → 0.20배, VC=50+ → 1.0배
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
if watch_count >= QUALITY_MIN_WC:
    quality = avg(completion_rate) × avg(satisfaction)
else:
    quality = 0
```

- completion_rate: 0~1 (완주율)
- satisfaction: 0~1 (베이지안 만족도)
- 둘의 곱: 완주하면서 만족한 콘텐츠가 높은 점수
- `QUALITY_MIN_WC = 5` — 시청 5건 미만이면 quality=0 (v2 추가)
  - WC=1일 때 completion×satisfaction이 우연히 높아지는 과대평가 방지

### 가중치 비교표

| 컴포넌트 | Stage 1 (cold) | Stage 2 (warm) | 역할 |
|---------|---------------|----------------|------|
| watch_heat (자체 인기) | 0 | **0.45** | 우리 플랫폼 실제 인기 |
| quality (자체 품질) | 0 | **0.25** | 완주율 × 만족도 |
| vote_score (외부 평판) | **0.65** | 0.15 | TMDB 평점 (신뢰도 보정) |
| freshness (최신성) | **0.35** | 0.15 | 출시 1년 이내 가산 |

### 전환 로직 (선형 보간)

```python
WARM_THRESHOLD = 10  # 시청 이력 10건 이상이면 Stage 2

if watch_count >= WARM_THRESHOLD:
    score = score_warm
else:
    blend = watch_count / WARM_THRESHOLD  # 0.0 ~ 1.0
    score = (1 - blend) * score_cold + blend * score_warm
```

- 10건 미만: cold↔warm **선형 보간** → 급격한 점수 변동 방지
- 10건 이상: 완전 warm 전환
- 기존 2023 VOD: watch_history 충분 → **처음부터 Stage 2**
- v1에서 30 → v2에서 10으로 하향: 100건 테스트에서 warm VOD가 8→27개로 증가, 자체 시청 시그널 반영 범위 확대

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

## 7. 확정 파라미터

| 파라미터 | v1 (초기) | v2 (확정) | 변경 사유 |
|---------|----------|----------|----------|
| `WARM_THRESHOLD` | 30 | **10** | 100건 테스트에서 warm VOD 8→27개로 증가 |
| `QUALITY_MIN_WC` | (없음) | **5** | WC=1 quality=0.577 과대평가 방지 |
| `VC_CREDIBILITY_CAP` | (없음) | **50** | VA=10.0/VC=1 vote_score 과대평가 방지 |

---

## 8. 실데이터 검증 (100건 테스트)

### 8-1. 테스트 설계

watch_count 분포를 고려하여 5개 구간에서 각 20건씩 층화 추출:

| 구간 | watch_count 범위 | 건수 | 비고 |
|------|-----------------|------|------|
| Tier 1 | 상위 (50+) | 20 | warm 확정 |
| Tier 2 | 중상위 (20~49) | 20 | warm 확정 |
| Tier 3 | 중위 (5~19) | 20 | warm / blend |
| Tier 4 | 하위 (2~4) | 20 | blend |
| Tier 5 | 최하위 (1) | 20 | blend (cold에 가까움) |

TMDB 평점은 `search/multi` → `movie/{id}` or `tv/{id}` detail API로 수집.
100건 중 83건에서 TMDB 매칭 성공 (17건은 VA=0, VC=0).

### 8-2. v1 → v2 개선 결과

| 문제 | v1 결과 | v2 결과 | 판정 |
|------|---------|---------|------|
| WC=1 quality 과대평가 | quality=0.577 (우연히 높은 완주율×만족도) | quality=0 (QUALITY_MIN_WC=5 필터) | **해결** |
| Low VC + High VA 과대평가 | 배견궁주대인 VA=10.0/VC=1 → vote_score 과대 | vote_score=0.0016 (VC credibility 댐핑) | **해결** |
| Warm VOD 부족 | 8/100 (THRESHOLD=30) | 27/100 (THRESHOLD=10) | **해결** |
| freshness=0 (2023 데이터) | 전부 0 | 전부 0 (예상대로) | 신규 VOD 유입 시 자연 해소 |

### 8-3. v2 Top 15 결과

| # | VOD | Score | Stage | VA | VC | WC | vote_score | watch_heat | quality |
|---|-----|-------|-------|----|----|----|-----------|-----------|---------|
| 1 | 블라인드 15회 | 0.5633 | warm | 7.4 | 2,520 | 50 | 0.6584 | 0.8658 | 0.300 |
| 2 | 기황후 25회 | 0.5611 | warm | 7.4 | 64 | 86 | 0.3519 | 1.0000 | 0.233 |
| 3 | 육룡이 나르샤 09회 | 0.5572 | warm | 7.2 | 31 | 62 | 0.1762 | 1.0000 | 0.323 |
| 4 | 오은영 리포트 결혼 지옥 16회 | 0.4943 | warm | 6.0 | 2 | 239 | 0.0030 | 1.0000 | 0.175 |
| 5 | 이누야샤 2기 21회 | 0.4481 | blend(0.10) | 8.6 | 2,058 | 1 | 0.7455 | 0.017 | 0.000 |
| 6 | 전원일기 0889회 | 0.3850 | warm | 7.6 | 149 | 24 | 0.4338 | 0.416 | 0.532 |
| 7 | 맨인블랙박스 257회 | 0.3774 | warm | 0.0 | 0 | 41 | 0.0000 | 0.710 | 0.232 |
| 8 | 일지매 16회 | 0.3737 | warm | 6.9 | 27 | 37 | 0.1414 | 0.641 | 0.257 |
| 9 | 이누야샤 1기 24회 | 0.3479 | blend(0.40) | 8.6 | 2,058 | 4 | 0.7455 | 0.069 | 0.000 |
| 10 | 아가사 크리스티: 명탐정 포와로 2 08회 | 0.3258 | blend(0.20) | 8.2 | 533 | 2 | 0.5866 | 0.035 | 0.000 |
| 11 | 전원일기 0673회 | 0.3239 | warm | 7.6 | 149 | 15 | 0.4338 | 0.260 | 0.568 |
| 12 | 1박2일 시즌4 15회 | 0.3081 | warm | 7.1 | 28 | 31 | 0.1525 | 0.537 | 0.175 |
| 13 | 친애하는 판사님께 10회 | 0.3057 | warm | 7.3 | 19 | 29 | 0.0947 | 0.502 | 0.262 |
| 14 | 스토브리그 11회 | 0.2999 | warm | 8.3 | 48 | 26 | 0.3532 | 0.450 | 0.177 |
| 15 | 마이 맨 | 0.2856 | blend(0.20) | 7.6 | 385 | 2 | 0.5135 | 0.035 | 0.000 |

### 8-4. VC credibility 댐핑 효과 (Low VC + High VA 케이스)

| VOD | VA | VC | v2 vote_score | 비고 |
|-----|----|----|--------------|------|
| 싱어게인 10회 | 9.5 | 2 | 0.0048 | VC credibility = 0.04 |
| 어서와 한국은 처음이지? 174회 | 8.7 | 3 | 0.0082 | VC credibility = 0.06 |
| 배견궁주대인 12회 | 10.0 | 1 | 0.0016 | VC credibility = 0.02 |
| 아무튼 출근 31회 | 9.0 | 1 | 0.0014 | VC credibility = 0.02 |
| 터닝메카드 33회 | 8.0 | 4 | 0.0117 | VC credibility = 0.08 |

→ 평가자 수가 극소인 고평점 VOD의 vote_score가 적절히 억제됨.

### 8-5. 스코어 분포

```
min    = 0.0008
max    = 0.5633
mean   = 0.1308
median = 0.0750
```

- Cold에 가까운 blend(0.10) VOD가 73건으로 분포가 낮은 쪽에 편중 (2023 데이터의 freshness=0 영향)
- 신규 VOD 유입 시 freshness 가산으로 분포가 상향 이동할 것으로 예상

### 8-6. 직관성 평가

- **Warm 상위**: 블라인드·기황후·육룡이나르샤 — 실제 인기 드라마 + 높은 시청량 → 합리적
- **오은영 리포트 4위**: WC=239 최다 시청이지만 VA=6.0/VC=2 낮은 외부 평판 → warm 공식에서 vote_score 비중 15%라 적절히 균형
- **이누야샤 5위**: WC=1이지만 VA=8.6/VC=2058 높은 TMDB 평판 → blend(0.10)으로 cold 공식 비중 90%, vote_score 주도 → 합리적
- **맨인블랙박스 7위**: TMDB 미매칭(VA=0)이지만 WC=41로 자체 인기 → warm에서 watch_heat만으로 순위 확보 → 시스템이 TMDB 의존 없이도 작동

---

## 9. 산출 예시 (v2 실데이터 기반)

### Case 1: 블라인드 15회 (Warm, 1위)

```
watch_count = 50 (>= 10 → warm)

vc_credibility = min(2520, 50) / 50 = 1.0
vote_score  = (7.379/10) × log(2521) / log(max_vc+1) × 1.0 = 0.6584
freshness   = 0 (2011년 출시)
watch_heat  = 0.8658 (정규화)
quality     = 0.5556 × 0.5396 = 0.300

score_warm  = 0.45×0.8658 + 0.25×0.300 + 0.15×0.6584 + 0.15×0
            = 0.3896 + 0.0750 + 0.0988 + 0
            = 0.5633
```

### Case 2: 이누야샤 2기 21회 (Blend 0.10, 5위)

```
watch_count = 1 (< 10 → blend)
blend       = 1 / 10 = 0.10

vc_credibility = min(2058, 50) / 50 = 1.0
vote_score  = (8.6/10) × log(2059) / log(max_vc+1) × 1.0 = 0.7455
freshness   = 0

score_cold  = 0.65 × 0.7455 + 0.35 × 0 = 0.4846
score_warm  = 0.45 × 0.0173 + 0.25 × 0 + 0.15 × 0.7455 + 0.15 × 0 = 0.1196

score       = 0.90 × 0.4846 + 0.10 × 0.1196
            = 0.4361 + 0.0120
            = 0.4481
```

### Case 3: 배견궁주대인 12회 (VC credibility 댐핑 사례)

```
watch_count = 1 (blend = 0.10)

vc_credibility = min(1, 50) / 50 = 0.02
vote_score  = (10.0/10) × log(2) / log(max_vc+1) × 0.02 = 0.0016
freshness   = 0

score_cold  = 0.65 × 0.0016 + 0.35 × 0 = 0.0010
score_warm  = 0.45 × 0.0173 + 0.25 × 0 + 0.15 × 0.0016 + 0.15 × 0 = 0.0080

score       = 0.90 × 0.0010 + 0.10 × 0.0080
            = 0.0009 + 0.0008
            = 0.0017
```

→ VA=10.0 만점이지만 VC=1이므로 최하위권 (0.0017). 댐핑 없었으면 상위 진입했을 것.

---

## 10. 향후 작업

| 순서 | 작업 | 브랜치 | 비고 |
|------|------|--------|------|
| 1 | vod 테이블 마이그레이션 (tmdb_vote_* 3개 컬럼) | `Database_Design` | 마이그레이션 SQL 작성 + VPC 실행 |
| 2 | RAG 파이프라인에 3개 필드 추출 추가 | `RAG` | meta_sources.py 수정 |
| 3 | 기존 VOD 일괄 TMDB 평점 수집 스크립트 | `RAG` 또는 별도 | 166K건 일괄 수집 |
| 4 | 인기도 산출 배치 스크립트 구현 | `CF_Engine` 또는 `gen_sentence` | 주 1회 실행 |
| 5 | popular_recommendation 적재 파이프라인 | 동일 | DELETE + INSERT (장르 단위) |
| 6 | API 엔드포인트 구현 | `API_Server` | `GET /recommend/popular?genre=영화` |

---

## 11. 가중치 튜닝 가이드

초기 가중치는 경험적 추정이다. 실 데이터 적재 후 아래 방법으로 조정한다:

1. **정성 평가**: 장르별 Top-20 결과를 사람이 보고 "이상한 순위" 식별
2. **A/B 테스트**: 가중치 조합 2~3개를 비교 (CTR, 체류 시간)
3. **격자 탐색**: α, β, γ, δ 를 0.05 단위로 변경하며 nDCG 등 랭킹 메트릭 측정

가중치 변경 시 이 문서를 업데이트한다.
