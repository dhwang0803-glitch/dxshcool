# Phase 1: 환경 설정 & 파일럿 (100건)

**단계**: Phase 1 / 4
**목표**: 로컬 LLM 환경 구성 + 검색/검증 함수 개발 + 100건 파일럿 테스트
**산출물**: `src/search_functions.py`, `src/validation.py`, `reports/phase1_report.md`
**선행 조건**: Ollama 설치, vod 테이블 rag 추적 컬럼 추가 완료

---

## 1. 환경 설정

### 1.1 로컬 LLM (Ollama + Kullm-12B)

```bash
# Ollama 설치 확인
ollama --version

# Kullm 모델 다운로드 (int4 양자화, ~6GB)
ollama pull kullm:12b-instruct-q4_0

# 서버 시작
ollama serve  # 백그라운드
```

### 1.2 Python 패키지

```bash
pip install requests wikipedia-api sentence-transformers chromadb python-dotenv psycopg2-binary
```

### 1.3 config/api_keys.env

```
IMDB_API_KEY=your_key_here
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=kullm:12b-instruct-q4_0
```

### 1.4 vod 테이블 추적 컬럼 추가 (VPC DB)

```sql
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_processed     BOOLEAN   DEFAULT FALSE;
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_source        VARCHAR(50);
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_processed_at  TIMESTAMPTZ;
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_confidence    REAL;
```

---

## 2. 구현 파일

### 2.1 src/search_functions.py

| 함수 | 검색 소스 | 반환값 |
|------|----------|--------|
| `search_director(asset_nm)` | Wikipedia → IMDB 폴백 | `str \| None` |
| `search_cast_lead(asset_nm, genre)` | IMDB → Wikipedia 폴백 | `list[str]` (최대 3명) |
| `search_rating(asset_nm)` | KMRB → IMDB 폴백 | `str \| None` (예: "15세이상관람가") |
| `search_release_date(asset_nm)` | IMDB → Wikipedia 폴백 | `str \| None` (YYYY-MM-DD) |

**폴백 전략**:
1. 1차 소스 검색 실패 시 → 2차 소스
2. 2차도 실패 시 → `None` 반환 (수동 검증 큐에 기록)

### 2.2 src/validation.py

| 함수 | 검증 내용 | 반환값 |
|------|----------|--------|
| `validate_director(name)` | 한국어/영어 인명 패턴, 길이 2~30자 | `bool` |
| `validate_cast(names)` | 인명 리스트 각각 검증, 최대 3명 | `bool` |
| `validate_rating(rating)` | 허용 등급 집합 포함 여부 | `bool` |
| `validate_date(date_str)` | YYYY-MM-DD 형식, 1900~2030 범위 | `bool` |
| `confidence_score(result, source, column)` | 소스 신뢰도 × 형식 일치도 | `float (0~1)` |

**허용 rating 값**:
```python
VALID_RATINGS = {'전체관람가', '12세이상관람가', '15세이상관람가', '18세이상관람가', '청소년관람불가', 'G', 'PG', 'PG-13', 'R', 'NC-17'}
```

---

## 3. 파일럿 테스트 (100건)

### 3.1 샘플 선정 기준

```python
# CT_CL 기준 층화추출 (VOD_Embedding 파일럿과 유사)
# director 결측 VOD 중 asset_nm 기준 다양성 확보
# 100건 = director 40건 + cast_lead 30건 + rating 20건 + release_date 10건
```

### 3.2 파일럿 성공 기준

| 지표 | 목표 |
|------|------|
| 검색 성공률 | ≥ 80% (80건 이상 non-NULL 반환) |
| 검증 통과율 | ≥ 90% (검색 결과 중 형식 유효) |
| 평균 처리 시간 | ≤ 10초/건 |
| 신뢰도 평균 | ≥ 0.80 |

---

## 4. 테스트 항목 (tests/test_phase1_pilot.py)

| ID | 항목 | 기대값 |
|----|------|--------|
| P1-01 | Ollama 서버 연결 | HTTP 200 |
| P1-02 | search_director("기생충") | "봉준호" 포함 |
| P1-03 | search_director("존재하지않는영화xyz") | None |
| P1-04 | search_cast_lead("기생충", "드라마") | 배우 목록 1명 이상 |
| P1-05 | search_rating("기생충") | VALID_RATINGS 내 값 |
| P1-06 | search_release_date("기생충") | "2019-05-30" |
| P1-07 | validate_director("봉준호") | True |
| P1-08 | validate_director("") | False |
| P1-09 | validate_rating("존재안하는등급") | False |
| P1-10 | validate_date("2019-05-30") | True |
| P1-11 | validate_date("2019-13-01") | False |
| P1-12 | confidence_score("봉준호", "IMDB", "director") | ≥ 0.8 |
| P1-13 | 파일럿 100건 검색 성공률 | ≥ 80% |
| P1-14 | vod 테이블 rag 추적 컬럼 존재 | 4개 컬럼 모두 존재 |
| P1-15 | 평균 처리 시간 | ≤ 10초/건 |

---

## 5. 주의사항

1. **API Rate Limit**: IMDB API는 일 500건 제한 → 파일럿에서 캐싱 필수
2. **한국어 영화 우선**: Wikipedia KO 검색 → 실패 시 EN 검색
3. **Ollama 미실행 시**: 테스트 P1-01 FAIL → 이후 테스트 skip
4. **처리 시간 목표**: LLM 추론 5-10초/건 × 100건 = 약 15분 (파일럿)

---

**다음 단계**: PLAN_02_HIGH_PRIORITY.md
