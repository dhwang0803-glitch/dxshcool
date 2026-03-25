# Normal_Recommendation — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

Cold Start 유저 및 비개인화 추천 대응을 위한 **일반 추천 엔진** +
로그인 유저 대상 **개인화 배너 추천** 생성.

### Pipeline A — 비개인화 인기 추천 (기존, 구현 완료)

시청 이력이 없는 신규 유저에게 CT_CL별 인기 VOD를 추천.
**추천 대상 CT_CL (고정 4개)**: 영화 / TV드라마 / TV 연예/오락 / TV애니메이션 — 각 Top-20
→ `serving.popular_recommendation` 적재

### Pipeline B — 개인화 배너 추천 (신규, 미구현)

로그인 유저의 시청 이력(`watch_history`)을 분석하여 **유저별 배너 Top 5** 생성.
프론트엔드 히어로 배너 캐러셀에 표시되며, 비로그인/신규 유저는 Pipeline A로 fallback.
→ `serving.personalized_banner` 적재

## 파일 위치 규칙 (MANDATORY)

```
Normal_Recommendation/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← yaml, .env.example
└── docs/      ← 설계 문서, 실험 리포트
```

| 파일 종류 | 저장 위치 | Pipeline |
|-----------|-----------|----------|
| 인기 VOD 집계 로직 | `src/popularity.py` | A |
| 개인화 배너 추천 로직 | `src/personalized_banner.py` | B (신규) |
| DB 연결 공통 모듈 | `src/db.py` | 공통 |
| 인기 추천 결과 생성 | `scripts/run_pipeline.py` | A |
| 개인화 배너 결과 생성 | `scripts/run_personalized_banner.py` | B (신규) |
| 추천 결과 DB 적재 | `scripts/export_to_db.py` | A |
| pytest | `tests/` | 공통 |
| 설정값 (top_n 등) | `config/recommend_config.yaml` | 공통 |

**`Normal_Recommendation/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import psycopg2
import pandas as pd
from dotenv import load_dotenv
```

## 추천 파이프라인

### Pipeline A — 비개인화 인기 추천 (구현 완료)

```
vod 테이블 (tmdb_vote_average, tmdb_vote_count, release_date, series_nm) 로드
watch_history 시청 통계 집계 (watch_count, watch_count_7d, completion_rate, satisfaction)
    → series_nm 기준 시리즈 집약
    → 2단계 인기 점수 계산 (cold/warm/blend)
    → CT_CL별(영화/TV드라마/TV 연예/오락/TV애니메이션) Top-20 생성
    → parquet 저장 → 조장에게 전달 → DB 적재
```

### Pipeline B — 개인화 배너 추천 (미구현)

```
유저별 watch_history 시청 이력 로드
    → 유저별 선호 장르(genre) 분포 집계 (시청 횟수 기반)
    → 선호 장르 내 인기 VOD 후보 풀 구성 (Pipeline A의 인기 점수 활용)
    → 유저별 시청 완료 콘텐츠 제외
    → 개인화 점수 계산:
        personalized_score = α × popularity_score + (1 - α) × genre_affinity
    → 유저별 Top 5 선별
    → serving.personalized_banner 적재
```

**개인화 점수 파라미터 (미확정, 실험 필요)**:
| 파라미터 | 초기값 | 설명 |
|---------|--------|------|
| `α` (alpha) | 0.5 | 인기도 vs 장르 친밀도 가중치 |
| `banner_top_n` | 5 | 유저별 배너 추천 개수 |
| `genre_affinity` | 시청비중 | 해당 장르 시청 횟수 / 전체 시청 횟수 |

**Pipeline B 대상 유저**: `watch_history`에 시청 이력이 1건 이상 있는 유저.
시청 이력이 없는 유저는 API_Server에서 Pipeline A(`popular_recommendation`) top 5로 fallback.

## 인기 점수 계산 방식

### 2단계 전략 (POPULARITY_SCORE_DESIGN.md 기준)

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

### 시리즈 집약 기준

- `series_nm` 기준으로 그룹핑 — 동일 시리즈는 **1개**만 추천
- `series_nm` NULL인 경우 단편/독립작품으로 간주, 개별 VOD 그대로 처리
- tmdb_vote_average: 시리즈 내 에피소드 평균
- tmdb_vote_count: 시리즈 내 에피소드 합산
- release_date: 시리즈 내 가장 최신 에피소드 기준

## 전제 조건

1. `Database_Design` 마이그레이션 완료 ✅ — `vod` 테이블에 `tmdb_vote_average`, `tmdb_vote_count`, `tmdb_popularity` 컬럼 추가
2. TMDB 평점 수집 완료 ✅ — 169,581건 중 126,168건 (74%) 적재

## 업데이트 주기

| Pipeline | 주기 | 비고 |
|----------|------|------|
| A (인기 추천) | 1주일 1회 수동 실행 | 매주 월요일 오전 권장 |
| B (개인화 배너) | 1주일 1회 수동 실행 | Pipeline A 실행 후 순차 실행 (인기 점수 의존) |

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 용도 | Pipeline |
|--------|------|------|----------|
| `public.vod` | `full_asset_id`, `genre`, `ct_cl`, `release_date`, `series_nm`, `tmdb_vote_average`, `tmdb_vote_count`, `poster_url`, `asset_nm` | VOD 메타데이터 | A, B |
| `public.watch_history` | `user_id_fk`, `vod_id_fk`, `strt_dt`, `completion_rate`, `satisfaction` | 시청 통계 집계 | A, B |
| `serving.popular_recommendation` | `vod_id_fk`, `score` | Pipeline A 인기 점수를 B에서 재활용 | B |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 비고 | Pipeline |
|--------|------|------|----------|
| `serving.popular_recommendation` | `ct_cl`, `rank`, `vod_id_fk`, `score`, `recommendation_type`, `expires_at` | UNIQUE(ct_cl, rank), TTL=7일 | A |
| `serving.personalized_banner` | `user_id_fk`, `rank`, `vod_id_fk`, `score`, `genre`, `expires_at` | UNIQUE(user_id_fk, rank), TTL=7일 | B (신규 테이블) |

### API_Server 소비 관계

| API 엔드포인트 | 배너 3단 구조 | 소스 |
|---------------|---------------|------|
| `GET /home/banner` (로그인) | 1단: personalized_banner(5) + 2단: popular(5) + 3단: hybrid(10) | JWT 선택적 인증 |
| `GET /home/banner` (비로그인) | 2단: popular(5)만 | 인증 불요 |
| `GET /home/sections` | — | `serving.popular_recommendation` (CT_CL × top 20) |
| `GET /home/sections/{user_id}` | — | `serving.popular_recommendation` + `watch_history` 장르 비중 |
