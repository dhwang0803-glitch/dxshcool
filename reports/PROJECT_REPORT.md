# VOD 추천 시스템 — 프로젝트 전체 보고서

**작성일**: 2026-03-09
**작성자**: Data Engineering + AI Team
**대상**: 팀 협의용 (전 브랜치 통합 현황)

---

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [데이터 규모 및 인프라](#2-데이터-규모-및-인프라)
3. [브랜치별 작업 현황](#3-브랜치별-작업-현황)
   - 3-1. Database_Design
   - 3-2. VOD_Embedding
   - 3-3. RAG
4. [전체 타임라인](#4-전체-타임라인)
5. [현재 이슈 및 의사결정 필요 사항](#5-현재-이슈-및-의사결정-필요-사항)
6. [다음 단계 로드맵](#6-다음-단계-로드맵)

---

## 1. 프로젝트 개요

VOD 추천 시스템을 구축하기 위해 세 개의 독립 파이프라인을 병렬 개발 중입니다.

| 파이프라인 | 브랜치 | 목표 | 현재 상태 |
|---|---|---|---|
| DB 설계 & 최적화 | `Database_Design` | PostgreSQL 스키마 + 성능 튜닝 + pgvector 통합 | **완료** |
| 영상 임베딩 | `VOD_Embedding` | 트레일러 수집 → CLIP 임베딩 → pgvector 적재 | **파일럿 완료** |
| 메타데이터 결측치 보완 | `RAG` | 외부 API 검색으로 73,000건 결측치 자동 채우기 | **Approach B v3 파일럿 완료** |

---

## 2. 데이터 규모 및 인프라

### 데이터 규모

| 항목 | 수량 |
|---|---|
| 전체 VOD 수 | **166,159건** |
| 사용자 수 | **242,702명** |
| 시청 이력 수 | **3,992,530건** |
| 메타데이터 결측치 타겟 | **~73,000건** (4개 컬럼) |

### 인프라

| 구분 | 스펙 |
|---|---|
| DB 서버 | PostgreSQL 18 on VPC (host: 10.0.0.1:5432) |
| DB 이름 | `prod_db` |
| pgvector | 설치 완료, 512차원 벡터 컬럼 (`embedding`) |
| 로컬 환경 | Windows 11, Python 3.x (`anaconda3/envs/myenv`) |
| LLM (로컬) | Ollama `exaone3.5:7.8b` (4.8GB) — RAG 폴백용 |
| 임베딩 모델 | CLIP ViT-B/32 (OpenAI, 512차원) |

---

## 3. 브랜치별 작업 현황

---

### 3-1. Database_Design 브랜치

**목표**: VOD 추천 시스템을 위한 PostgreSQL 데이터베이스 설계, 마이그레이션, 성능 최적화, pgvector 통합

#### Phase 1 — 스키마 설계 및 DDL (완료)

- **설계 원칙**: 3NF 정규화, PostgreSQL 전환 (MySQL → Postgres)
- **주요 테이블**: `vod`, `users`, `watch_history`, `genre`, `vod_genre`, `ratings`, `recommendations`
- **pgvector 통합**: `vod` 테이블에 `embedding VECTOR(512)` 컬럼 추가
- **테스트 결과**: **60/60 스키마 테스트 PASS** (VPC DB 실행)
- **핵심 설계 결정**:
  - `watch_history` 파티셔닝 → 주간(weekly) 파티션 채택
  - UUID 대신 SERIAL PK (성능 우선)
  - `rag_processed`, `rag_source`, `rag_processed_at`, `rag_confidence` 컬럼 추가 (RAG 파이프라인 추적용)

#### Phase 2 — 데이터 마이그레이션 (완료)

- MySQL → PostgreSQL 데이터 마이그레이션 스크립트 구현
- VPC 연결 타임아웃 버그 수정 (`migrate.py`)
- 통합 테스트 모두 PASS

#### Phase 3 — 성능 최적화 (완료)

**3A: 파티셔닝 & 기본 인덱스**
- `watch_history` 주간 파티션 적용
- pgvector IVFFlat 인덱스 설정

**3B-OPT1: 인덱스 최적화** (1차 시도)
- Covering index 추가 (`vod_genre`, `watch_history`)
- Partial index (활성 사용자 대상)
- `random_page_cost = 1.5` 조정 (SSD 최적화)
- 결과: P01, P05 PASS / P04, P06 여전히 미달

**3B-OPT2: Materialized View** (최종 해결)
- P04 (`genre별 시청 통계`) → MV 적용 → PASS
- P06 (`사용자 추천 피드`) → MV 적용 → PASS
- **최종: 6개 성능 테스트 모두 PASS** (P01~P06)

#### Phase 4 — VOD 인제스트 파이프라인 (완료)

- pgvector 임베딩 적재 파이프라인 (`ingest_to_db.py`) 완성
- **테스트 결과: 17/17 PASS** (vod_embedding + vod_recommendation 전체)

#### 주요 파일

```
Database_Design/
├── agents/           # TDD 에이전트 지시사항 (TestWriter, Developer, Tester, Refactor, Reporter)
├── plans/
│   ├── PLAN_00_MASTER.md
│   ├── PLAN_01_SCHEMA_DESIGN.md
│   ├── PLAN_02_MIGRATION.md
│   ├── PLAN_03_PERFORMANCE.md
│   └── PLAN_04_VECTOR_SEARCH.md
├── src/
│   ├── schema.sql       # DDL (3NF, pgvector)
│   ├── migrate.py       # 마이그레이션 스크립트
│   └── ingest_to_db.py  # pgvector 적재
├── tests/
│   └── phase4_test.py   # 17/17 PASS
└── reports/
    └── performance_test_results.md
```

---

### 3-2. VOD_Embedding 브랜치

**목표**: YouTube 트레일러 수집 → CLIP 임베딩 → pgvector 적재 (영상 기반 유사도 추천)

#### 파이프라인 구성

```
PLAN_01: crawl_trailers.py
  yt-dlp로 YouTube 트레일러 수집 (asset_nm → 검색 → 다운로드)
  저장 경로: <DATA_DIR>/trailers/

PLAN_02: batch_embed.py
  CLIP ViT-B/32 모델로 512차원 임베딩 추출
  배치 크기: 100건, GPU 미사용(CPU)

PLAN_03: ingest_to_db.py
  pgvector 적재 (vod.embedding 컬럼)
  배치: 100건씩 upsert
```

#### 파일럿 결과 (100건, 2026-03-08)

| 단계 | 성공 | 실패 | 성공률 |
|---|---|---|---|
| 트레일러 크롤링 | 98 | 2 | **98%** |
| CLIP 임베딩 | 78 | 22 | **78%** |
| pgvector 적재 | 78 | 0 | **100%** |

임베딩 실패 22건 중 8건은 동일 파일 공유 cascade 실패 (실질 원인 4건).

#### 버그 수정 이력 (4건)

| 버그 | 증상 | 수정 |
|---|---|---|
| `normalize_title()` | "1724기방난동사건" → 검색 실패 | 숫자-한글 경계에 공백 삽입 |
| `strip_episode_suffix()` | "파리의연인01화" 미처리 | `\s+` → `\s*` |
| `duration_filter()` | 불완전 영상 전건 no_result | `if incomplete: return None` 추가 |
| `dedup_by_series()` | 파일럿 중복 처리 오류 | Full 운영에서 제거 예정 |

#### Full 운영 개선 사항 (미완료)

- 현재 파일럿 100건 처리 완료, Full 166,159건은 미실행
- GPU 가속 (현재 CPU only) 적용 시 임베딩 속도 대폭 개선 가능
- `dedup_by_series()` 파이럿 전용 로직 제거 필요

#### 주요 파일

```
VOD_Embedding/
├── src/
│   ├── crawl_trailers.py  # yt-dlp 크롤러
│   ├── batch_embed.py     # CLIP 임베딩
│   └── ingest_to_db.py    # pgvector 적재
├── plans/
│   ├── PLAN_01_CRAWL.md
│   ├── PLAN_02_EMBED.md
│   └── PLAN_03_INGEST.md
└── reports/
    └── report.md          # 파일럿 결과 상세
```

---

### 3-3. RAG 브랜치

**목표**: 외부 API 검색으로 vod 테이블 메타데이터 결측치 자동 보완

#### 결측치 현황

| 컬럼 | 결측 건수 | 우선순위 | 목표 성공률 |
|---|---|---|---|
| `cast_lead` | 166,159건 (신규 컬럼) | HIGH | 90% |
| `cast_guest` | 166,159건 (신규 컬럼) | MEDIUM | 85% |
| `rating` | 166,159건 (신규 컬럼) | HIGH | 98% |
| `release_date` | 166,159건 (신규 컬럼) | HIGH | 95% |
| `director` | 27건 | HIGH | 95% |
| `smry` | 13건 | MEDIUM | 80% |

> 신규 컬럼 4개는 2026-03-09 ALTER TABLE로 추가됨.

#### Phase 1 — 기반 함수 구현 (완료)

**파일: `RAG/src/search_functions.py`**

검색 전략 (우선순위):
1. Wikipedia KO (다중쿼리)
2. Wikipedia EN
3. IMDB API (키 설정 시)
4. Ollama `exaone3.5:7.8b` 폴백

주요 버그 수정:
- "N 번째" 공백 포함 패턴: `\S+번째` → `\S+\s+번째`
- 감독상과/감독부문 오매칭: `감독\s*` → `감독\s+([가-힣]{2,5})(?![상부])`
- 조사 포함 이름 필터: `_KO_PARTICLES`로 `[과와이가은는을를의도로]$` 제거
- "가이 리치가 감독" 패턴: 혼합 패턴 추가

**파일: `RAG/src/validation.py`**

| 함수 | 역할 |
|---|---|
| `validate_director(name)` | 감독명 유효성 (2~40자, 한/영/중) |
| `validate_cast(names)` | 배우 리스트 유효성 (1~5명) |
| `validate_rating(rating)` | VALID_RATINGS 집합 매칭 |
| `validate_date(date_str)` | YYYY-MM-DD 형식 + 1900~2030 범위 |
| `confidence_score(result, source, column)` | 소스 기본 신뢰도 × 형식 일치 보너스 |

지원 등급 (VALID_RATINGS):
- 한국: 전체관람가, 7세이상관람가, 12세이상관람가, 14세이상관람가, 15세이상관람가, 18세이상관람가, 청소년관람불가
- 미국: G, PG, PG-13, R, NC-17

**테스트 결과**: P1-01 ~ P1-15 중 **14 PASS / 1 SKIP** (IMDB 키 미설정) / 0 FAIL

#### PLAN_00b — Approach 비교 실험 (파일럿 완료)

**목적**: 검색엔진 방식(A) vs TMDB 직접 파싱(B) 중 더 나은 방식 선택

**Approach A — 검색엔진 방식** (baseline)
- Wikipedia/IMDB 텍스트 파싱
- 파일럿 결과: 비교 기준값 (별도 run_a.log 참조)

**Approach B v3 — TMDB 직접 파싱**

아키텍처:
```
vod 테이블 (cast_lead IS NULL, 100건 층화추출)
  ↓
_series_name() → SeriesCache 키 생성
  ↓
SeriesCache miss → TMDB search/multi API 호출
  ↓
ct_cl 분기:
  영화 → movie/{id}?append_to_response=credits,release_dates
  TV드라마/애니 → tv/{id}?append_to_response=credits,content_ratings
  TV연예/오락 → tv/{id} (series MC) + episode/{ep} (guest_stars)
  ↓
_extract_cast() / _extract_rating() / _extract_director() / _extract_date()
  ↓
validation.py로 유효성 검증
  ↓
result_B.json 저장
```

주요 기능:
- **SeriesCache**: 시리즈명 기준 TMDB 결과 캐싱 (에피소드별 중복 API 호출 방지)
- **국제 등급 변환**: 21개국 등급 → 한국 영등위 자동 변환
  - 우선순위: JP → TW → HK → SG → US → GB → AU → FR → DE → RU → VN → IT → CA
- **타이틀 매칭 개선**:
  - 붙여쓰기 공백 삽입 (명탐정코난 → 명탐정 코난)
  - 후행 마침표 제거 (팬 암 1 14회.)
  - `with X` 부제 제거 (정글의 법칙 with 바탁)

**파일럿 결과 (100건 층화추출)**

| 컬럼 | 성공 건수 | 성공률 |
|---|---|---|
| `cast_lead` | 58/100 | **58%** |
| `rating` | 47/100 | **47%** |
| `release_date` | 69/100 | **69%** |
| `director` | 46/100 | **46%** |

**미매칭 패턴 분석**

| 분류 | 건수 | 처리 가능 여부 |
|---|---|---|
| TMDB 미등록 로컬 콘텐츠 (시사교양, 키즈 등) | ~22건 | KMDB API 키 필요 |
| 붙여쓰기 불일치 | 7건 | 수정 완료 |
| 후행 마침표 | 3건 | 수정 완료 |
| `with X` 부제 | 1건 | 수정 완료 |

**버그 수정 이력 (Approach B)**

| 버그 | 증상 | 수정 |
|---|---|---|
| `_KR_RATING_MAP` 오매핑 | rating 0% (이용가 vs 이상관람가) | 전체 매핑 재작성 (이상관람가 형식) |
| cast 상위 3명 제한 | TMDB 4명 표시 vs 3명 추출 | `[:4]` 변경 |
| 14세이상관람가 누락 | VALID_RATINGS 미포함 | 추가 + 숫자 자동 생성 폴백 |
| KR 등급 없는 콘텐츠 | rating 미추출 | 21개국 변환 테이블 추가 |

**주요 파일**

```
RAG/
├── src/
│   ├── search_functions.py   # Phase 1 검색 함수 (Wikipedia/IMDB/Ollama)
│   ├── validation.py         # 유효성 검증 + 신뢰도 점수
│   ├── extract_sample.py     # 100건 층화추출
│   ├── run_approach_a.py     # Approach A 배치 실행
│   └── run_approach_b.py     # Approach B v3 배치 실행 (TMDB)
├── data/
│   └── comparison_sample.csv # 100건 샘플 (ct_cl 비율 유지)
├── reports/
│   ├── result_A.json         # Approach A 결과
│   ├── result_B.json         # Approach B v3 결과 (최신)
│   ├── run_a.log
│   └── run_b.log
├── config/
│   ├── rag_config.yaml       # llm.model: exaone3.5:7.8b
│   └── api_keys.env.example
├── plans/
│   ├── PLAN_00_MASTER.md
│   ├── PLAN_00b_APPROACH_COMPARISON.md  ← 현재 진행 중
│   ├── PLAN_01_SETUP_PILOT.md           ← 완료
│   └── PLAN_02_HIGH_PRIORITY.md
└── tests/
    └── test_phase1_pilot.py  # 14P/1S/0F
```

---

## 4. 전체 타임라인

| 날짜 | 브랜치 | 주요 이정표 |
|---|---|---|
| 2026-02-19 | Database_Design | 프로젝트 초기화, TDD 에이전트 추가 |
| 2026-02-20 | Database_Design | Phase 1 스키마 DDL — 60/60 VPC 테스트 PASS |
| 2026-02-22 | Database_Design | Phase 2 마이그레이션 구현 — 통합 테스트 PASS |
| 2026-02-24 | Database_Design | Phase 3 성능 테스트 (multi-config 비교) |
| 2026-02-25 | Database_Design | 3B-OPT1: 인덱스 최적화 적용 |
| 2026-02-26 | Database_Design | 3B-OPT2: Materialized View → P04/P06 PASS |
| 2026-02-27 | Database_Design | Phase 3C/4: 주간 파티셔닝, pgvector, VOD ingest |
| 2026-02-28 | Database_Design | Security Auditor 에이전트 추가 |
| 2026-03-08 | VOD_Embedding | 파이프라인 초기화 (crawl/embed/ingest) |
| 2026-03-08 | VOD_Embedding | 파일럿 100건 실행 — 98% 크롤링, 78% 임베딩 |
| 2026-03-08 | RAG | 브랜치 초기화 — TDD 플랜, 에이전트 설정 |
| 2026-03-08 | RAG | Phase 1 구현 — search_functions + validation (14P/1S) |
| 2026-03-09 | RAG | DB 스키마 변경 — cast_lead/cast_guest/rating/release_date 컬럼 추가 |
| 2026-03-09 | RAG | PLAN_00b: 100건 층화추출 완료 |
| 2026-03-09 | RAG | Approach B v1~v3 개발 및 파일럿 실행 |
| 2026-03-09 | RAG | 등급 매핑 수정 (rating 0% → 47%), 국제 등급 변환 테이블 추가 |

---

## 5. 현재 이슈 및 의사결정 필요 사항

### 이슈 1 — Approach B vs A 최종 선택 (우선순위: 높음)

**현황**: Approach B (TMDB) v3 파일럿 완료. Approach A와 정량 비교 필요.

**결정 기준**:
- 정확도 차이 ≥ 5% → Approach B (TMDB) 채택
- 정확도 차이 < 5% AND 처리시간 B > 10초/건 → Approach A (검색엔진) 유지

**다음 액션**: `compare_results.py` 실행하여 A/B 정량 비교 리포트 생성

---

### 이슈 2 — TMDB 미매칭 로컬 콘텐츠 (~22% 미해결)

**증상**: 시사교양, 키즈 채널, 지역 방송 콘텐츠 등 TMDB 미등록 → 100건 중 약 22건 미추출

**해결 방안**:
- KMDB API (한국영상자료원) 키 발급 → 국내 콘텐츠 보완
- KMDB 연동 모듈 추가 개발 필요

**의사결정 필요**: KMDB API 키 발급 및 예산 확인

---

### 이슈 3 — rating 53% 여전히 미추출

**현황**: TMDB KR 등급 없는 콘텐츠 → 21개국 국제 변환 적용 후에도 53% 누락

**주요 원인**:
- 키즈/어린이 콘텐츠: TMDB에 등급 정보 자체 없음
- 중국/일본 드라마 일부: TMDB 등록 자체 없음
- 시사교양/다큐: 등급 미표시

**해결 방안**: KMDB API 보완 OR 장르 기반 기본값 할당 (예: 키즈 → 전체관람가)

---

### 이슈 4 — VOD_Embedding Full 운영 미실행

**현황**: 파일럿 100건 완료, Full 166,159건 미실행

**선결 사항**:
- GPU 서버 또는 클라우드 배치 환경 확보 (CPU only 시 예상 수십 시간)
- `dedup_by_series()` 파이럿 전용 로직 제거
- Full 운영용 배치 크기 및 에러 처리 강화

---

### 이슈 5 — DB UPDATE 미완료

**현황**: Approach B 결과가 `result_B.json`에 저장되어 있으나 실제 DB의 vod 테이블에는 아직 반영 미완료

**다음 액션**: A/B 비교 완료 → 채택된 방식의 결과로 DB UPDATE SQL 실행

---

## 6. 다음 단계 로드맵

### 단기 (1~2주)

| 순서 | 작업 | 담당 | 예상 기간 |
|---|---|---|---|
| 1 | `compare_results.py` — A/B 정량 비교 리포트 | RAG팀 | 1일 |
| 2 | Approach 최종 결정 (팀 협의) | 전체 | 즉시 |
| 3 | 채택 방식으로 Full 166,159건 처리 | RAG팀 | 1~2주 |
| 4 | 결과 DB UPDATE + 품질 샘플 검증 (5%) | RAG팀 | 2~3일 |
| 5 | KMDB API 키 발급 (미매칭 콘텐츠 보완) | 담당자 협의 | 별도 |

### 중기 (2~4주)

| 순서 | 작업 | 담당 | 예상 기간 |
|---|---|---|---|
| 1 | VOD_Embedding Full 운영 — GPU 환경 확보 | Infra팀 | 협의 |
| 2 | CLIP 임베딩 166,159건 전체 실행 | VOD_Embedding팀 | 확보 후 2~3일 |
| 3 | pgvector 기반 영상 유사도 추천 API 연동 | Backend팀 | 별도 |

### 장기

| 작업 | 비고 |
|---|---|
| RAG MEDIUM 우선순위 처리 (cast_guest, smry ~20,000건) | HIGH 완료 후 |
| 추천 시스템 모델 개발 (협업 필터링 + pgvector 하이브리드) | 전 파이프라인 완료 후 |
| 모니터링 & 품질 자동 검증 파이프라인 | 운영 단계 |

---

## 부록 — 브랜치별 테스트 요약

| 브랜치 | 테스트 파일 | 결과 |
|---|---|---|
| Database_Design | phase4_test.py | 17/17 PASS |
| Database_Design | schema 테스트 (Phase 1) | 60/60 PASS |
| VOD_Embedding | (수동 파일럿 검증) | 98% 크롤링, 78% 임베딩 |
| RAG | test_phase1_pilot.py | 14 PASS / 1 SKIP / 0 FAIL |
| RAG | Approach B v3 파일럿 | 100건, cast 58% / rating 47% / date 69% / dir 46% |

---

*본 보고서는 Claude Code (claude-sonnet-4-6)를 활용하여 자동 생성되었습니다.*
*2026-03-09 기준, 각 브랜치의 최신 커밋 및 실험 결과를 반영합니다.*
