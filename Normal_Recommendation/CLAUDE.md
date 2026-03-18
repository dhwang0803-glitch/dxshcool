# Normal_Recommendation — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

Cold Start 유저 및 비개인화 추천 대응을 위한 **일반 추천 엔진**.
시청 이력이 없는 신규 유저에게 장르별 인기 VOD를 추천하고,
결과를 DB에 저장하여 API_Server가 실시간으로 서빙할 수 있게 한다.

**추천 대상 장르 (고정 4개)**: 영화 / 드라마 / 예능 / 애니 — 각 Top-20

## 파일 위치 규칙 (MANDATORY)

```
Normal_Recommendation/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← yaml, .env.example
└── docs/      ← 설계 문서, 실험 리포트
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 인기 VOD 집계 로직 | `src/popularity.py` |
| DB 연결 공통 모듈 | `src/db.py` |
| 추천 결과 생성 실행 | `scripts/run_pipeline.py` |
| 추천 결과 DB 적재 | `scripts/export_to_db.py` |
| pytest | `tests/` |
| 설정값 (top_n 등) | `config/recommend_config.yaml` |

**`Normal_Recommendation/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import psycopg2
import pandas as pd
from dotenv import load_dotenv
```

## 추천 파이프라인

```
vod 테이블 (tmdb_vote_average, tmdb_vote_count, release_date, series_nm) 로드
watch_history 시청 통계 집계 (watch_count, watch_count_7d, completion_rate, satisfaction)
    → series_nm 기준 시리즈 집약
    → 2단계 인기 점수 계산 (cold/warm/blend)
    → 장르별(영화/드라마/예능/애니) Top-20 생성
    → parquet 저장 → 조장에게 전달 → DB 적재
```

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

## 전제 조건 (실행 전 필수)

1. `Database_Design` 마이그레이션 완료 — `vod` 테이블에 `tmdb_vote_average`, `tmdb_vote_count`, `tmdb_popularity` 컬럼 추가
2. `RAG` 파이프라인 수정 완료 — TMDB API 응답에서 3개 필드 수집 후 vod 테이블 적재

## 업데이트 주기

- **1주일 1회** 수동 실행 (조장이 매주 parquet 생성 후 DB 적재)
- 실행 시점: 매주 월요일 오전 권장

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 용도 |
|--------|------|------|
| `public.vod` | `full_asset_id`, `genre`, `ct_cl`, `release_date`, `series_nm`, `tmdb_vote_average`, `tmdb_vote_count` | 인기 기준 VOD 목록 |
| `public.watch_history` | `vod_id_fk`, `strt_dt`, `completion_rate`, `satisfaction` | 시청 통계 집계 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 비고 |
|--------|------|------|
| `serving.popular_recommendation` | `genre`, `rank`, `vod_id_fk`, `score`, `recommendation_type`, `expires_at` | UNIQUE(genre, rank), TTL=7일 |
