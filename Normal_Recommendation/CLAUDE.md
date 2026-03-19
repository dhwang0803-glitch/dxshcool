# Normal_Recommendation — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

Cold Start 유저 및 비개인화 추천 대응을 위한 **일반 추천 엔진**.
시청 이력이 없는 신규 유저에게 CT_CL별 인기 VOD를 추천하고,
결과를 DB에 저장하여 API_Server가 실시간으로 서빙할 수 있게 한다.

**추천 대상 CT_CL (고정 4개)**: 영화 / TV드라마 / TV애니메이션 / TV 연예/오락 — 각 Top-20

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
vod 테이블 (rating, release_date) 로드
    → 시리즈 기준 그룹핑 (에피소드 → 시리즈 단위로 집약)
    → 인기 점수 계산: rating + 최신성 가중치(release_date)
    → CT_CL별(영화/TV드라마/TV애니메이션/TV 연예/오락) Top-20 생성
    → parquet 저장 → 조장에게 전달 → DB 적재
```

## 인기 점수 계산 방식

### 공식

```
score = w_rating * norm(rating) + w_recency * recency_score(release_date)
```

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `w_rating` | 0.6 | rating 가중치 |
| `w_recency` | 0.4 | 최신성 가중치 |
| `top_n` | 20 | CT_CL별 추천 개수 |

### 최신성 점수 (recency_score)

- `release_date` 기준 min-max 정규화 (최신일수록 1에 가까움)
- `release_date` NULL인 경우 0으로 처리
- **최신이면서 rating이 높을수록 1순위**

### 시리즈 집약 기준

- `series_nm` 기준으로 그룹핑 — 동일 시리즈는 **1개**만 추천
- `series_nm` NULL인 경우 단편/독립작품으로 간주, 개별 VOD 그대로 처리
- rating: 시리즈 내 에피소드 평균값 사용
- release_date: 시리즈 내 가장 최신 에피소드 기준

## 업데이트 주기

- **1주일 1회** 수동 실행 (조장이 매주 parquet 생성 후 DB 적재)
- 실행 시점: 매주 월요일 오전 권장

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 용도 |
|--------|------|------|
| `public.vod` | `full_asset_id`, `genre`, `ct_cl`, `rating`, `release_date`, `series_nm` | 인기 기준 VOD 목록 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 비고 |
|--------|------|------|
| `serving.popular_recommendation` | `ct_cl`, `rank`, `vod_id_fk`, `score`, `recommendation_type`, `expires_at` | UNIQUE(ct_cl, rank), TTL=7일 |
