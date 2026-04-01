# RAG — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

VOD 메타데이터 결측치를 외부 소스에서 자동 수집하여 `public.vod` 테이블을 보강하는 파이프라인.
166,159건 VOD 대상, 시리즈 레벨 dedup으로 API 호출을 최소화한다.

## 데이터 소스 (폴백 체인)

| 순서 | 소스 | 주요 필드 | 비고 |
|------|------|-----------|------|
| 1 | **TMDB** | director, cast_lead, rating, release_date, smry | 시리즈당 1회 호출, 40 req/s |
| 2 | **KMDB** | cast_lead, rating, disp_rtm, director, release_date | Stage 1 미확보분만 |
| 3 | **JustWatch** | rating, disp_rtm, director, cast_lead, smry | GraphQL, Stage 2 미확보분만 |
| 4 | **DATA_GO** | rating, disp_rtm, director, cast_lead | 공공 API, 최종 폴백 |
| 보완 | **Naver** | cast_lead, cast_guest, director, rating, release_date | TV/영화 별도 파서, curl_cffi 비동기 |

## 파일 위치 규칙 (MANDATORY)

```
RAG/
├── src/                ← import 전용 라이브러리 (직접 실행 X)
│   ├── meta_sources.py       # TMDB/KMDB/JW/DATA_GO 검색 + 시리즈 dedup
│   ├── search_functions.py   # 단건 검색 함수 (TMDB→KMDB→AI-Hub→Ollama 폴백)
│   └── validation.py         # 결과 유효성 검증 (감독/배우/등급/날짜/신뢰도)
├── scripts/            ← 직접 실행 스크립트
│   ├── run_bulk_meta.py          # 대량 메타데이터 4단계 수집 (TMDB→KMDB→JW→DATA_GO)
│   ├── run_cast_guest.py         # cast_guest 전용 3단계 (TMDB credits→smry RAG→DB UPDATE)
│   ├── run_naver_meta.py         # 네이버 검색 기반 보완 (TV JSON + 영화 HTML)
│   └── fill_missing_episodes.py  # TMDB 누락 에피소드 INSERT (synthetic ID 생성)
├── tests/              ← pytest
│   └── test_phase1_pilot.py
├── plans/              ← 설계 문서
│   ├── PLAN_00_MASTER.md
│   ├── PLAN_00b_APPROACH_COMPARISON.md
│   ├── PLAN_01_SETUP_PILOT.md
│   ├── PLAN_02_HIGH_PRIORITY.md
│   ├── PLAN_03_QUALITY_MONITORING.md
│   └── PLAN_04_MEDIUM_PRIORITY.md
├── reports/            ← 실행 결과 리포트/JSON
├── config/             ← api_keys.env (gitignore 대상)
├── data/               ← CSV 원본, bulk 캐시 (gitignore 대상)
└── docs/               ← (비어있음, plans/reports에 분산)
```

## 기술 스택

```python
import requests           # TMDB, KMDB, DATA_GO, JustWatch API
from curl_cffi.requests import AsyncSession  # Naver 비동기 크롤링
from selectolax.parser import HTMLParser     # Naver 영화 HTML 파싱
from dotenv import load_dotenv               # .env 로드
from tqdm import tqdm                        # 진행률 표시
```

## 파이프라인 실행

```bash
# 1. 대량 메타데이터 수집 (TMDB→KMDB→JW→DATA_GO, 시리즈 dedup)
python RAG/scripts/run_bulk_meta.py --source db --output db
python RAG/scripts/run_bulk_meta.py --source db --resume --stages 234  # 재개

# 2. cast_guest 전용 수집
python RAG/scripts/run_cast_guest.py               # 전체
python RAG/scripts/run_cast_guest.py --stages 12   # Stage 1+2만
python RAG/scripts/run_cast_guest.py --dry-run     # DB 미반영

# 3. 네이버 보완 수집
python RAG/scripts/run_naver_meta.py --full --update  # 전체 + DB 반영
python RAG/scripts/run_naver_meta.py --tv-only        # TV만
python RAG/scripts/run_naver_meta.py --movie-only     # 영화만

# 4. 누락 에피소드 INSERT
python RAG/scripts/fill_missing_episodes.py            # 전체
python RAG/scripts/fill_missing_episodes.py --dry-run  # 확인만
python RAG/scripts/fill_missing_episodes.py --resume   # 체크포인트 재개
```

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` RAG 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id` | VARCHAR(64) | 처리 대상 식별 |
| `public.vod` | `asset_nm` | VARCHAR | 검색 쿼리, 시리즈명 추출, 에피소드 번호 파싱 |
| `public.vod` | `genre`, `ct_cl` | VARCHAR | 소스 선택 (영화/TV 분기), 에피소드 대상 필터 |
| `public.vod` | `series_nm` | VARCHAR | 시리즈 레벨 dedup 기준 |
| `public.vod` | `rag_processed` | BOOLEAN | FALSE인 레코드만 처리 |
| `public.vod` | `smry` | TEXT | cast_guest RAG 추출 입력 (Stage 2) |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.vod` | `director` | VARCHAR(255) | |
| `public.vod` | `cast_lead` | TEXT | |
| `public.vod` | `cast_guest` | TEXT | run_cast_guest.py 전용 |
| `public.vod` | `rating` | VARCHAR(16) | |
| `public.vod` | `release_date` | DATE | |
| `public.vod` | `smry` | TEXT | |
| `public.vod` | `series_nm` | VARCHAR | run_bulk_meta.py에서 갱신 |
| `public.vod` | `disp_rtm` | VARCHAR | 러닝타임 (KMDB/JW/DATA_GO) |
| `public.vod` | `rag_processed` | BOOLEAN | 완료 시 TRUE |
| `public.vod` | `rag_source` | VARCHAR(64) | TMDB/KMDB/JW/DATA_GO/NAVER |
| `public.vod` | `rag_processed_at` | TIMESTAMPTZ | |
| `public.vod` | `rag_confidence` | REAL | 0.0~1.0 |
| `public.vod` | *(INSERT)* | — | fill_missing_episodes: 누락 에피소드 신규 행 삽입 |

## 환경변수

```bash
# .env 또는 RAG/config/api_keys.env
TMDB_API_KEY=           # TMDB v3 API
TMDB_READ_ACCESS_TOKEN= # TMDB Bearer token
KMDB_API_KEY=           # 한국영화데이터베이스
DATA_GO_API_KEY=        # 공공데이터포털
DB_HOST=                # PostgreSQL
DB_PORT=
DB_USER=
DB_PASSWORD=
DB_NAME=
```

---

**마지막 수정**: 2026-04-01
**프로젝트 상태**: 파이프라인 구현 완료, 운영 중
