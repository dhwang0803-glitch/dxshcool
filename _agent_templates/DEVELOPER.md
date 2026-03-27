# Developer Agent 지시사항

## 역할
Test Writer Agent가 작성한 테스트를 통과하는 최소한의 코드를 구현한다 (TDD Green 단계).
과도한 설계나 불필요한 기능을 추가하지 않는다.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 테스트를 통과하는 가장 단순한 코드를 작성한다
3. **PLAN 준수**: 해당 Phase의 PLAN 파일 내용을 벗어나지 않는다
4. **외부 API 캐싱**: API 호출은 반드시 캐시 레이어를 거친다 (중복 요청 방지)

---

## Phase별 구현 파일 위치

| Phase | 구현 파일 | 위치 |
|-------|----------|------|
| Phase 1 | `search_functions.py` | `RAG/src/` |
| Phase 1 | `validation.py` | `RAG/src/` |
| Phase 2 | `rag_pipeline.py` | `RAG/src/` |
| Phase 3 | `monitoring.py` | `RAG/src/` |
| Phase 3 | `quality_analysis.py` | `RAG/src/` |

---

## Phase 1 구현 체크리스트

### search_functions.py
```
1. Ollama 쿼리 함수 (query_ollama)
2. Wikipedia 검색 함수 (search_wikipedia_ko)
3. IMDB 검색 함수 (search_imdb) - API key from config/api_keys.env
4. KMRB 검색 함수 (search_kmrb) - 공개 API
5. search_director: Wikipedia → IMDB 폴백
6. search_cast_lead: IMDB → Wikipedia 폴백
7. search_rating: KMRB → IMDB 폴백
8. search_release_date: IMDB → Wikipedia 폴백
9. 요청 간 sleep(0.5) 적용 (Rate Limit 준수)
10. 결과 캐시 (dict 또는 SQLite)
```

### validation.py
```
1. VALID_RATINGS 상수 정의
2. validate_director(name)
3. validate_cast(names)
4. validate_rating(rating)
5. validate_date(date_str)
6. confidence_score(result, source, column)
```

---

## Phase 2 구현 체크리스트

### rag_pipeline.py
```
1. RAGPipeline.__init__: config 로드, Ollama/Chroma/psycopg2 초기화
2. process_high_priority: 컬럼 순서대로 처리
3. _process_column: 배치 처리 + ThreadPoolExecutor (검색 IO 병렬)
4. _search_and_validate: search → validate → confidence_score
5. update_database: ON CONFLICT DO UPDATE, WHERE {column} IS NULL 조건
6. 체크포인트 저장/로드 (config/checkpoint.json)
7. generate_report: 통계 수집 후 reports/phase2_report.md 호출
```

---

## 환경변수 로드 방식

```python
from dotenv import load_dotenv
import os

load_dotenv('RAG/config/api_keys.env')

IMDB_API_KEY  = os.getenv('IMDB_API_KEY')
OLLAMA_HOST   = os.getenv('OLLAMA_HOST', 'http://localhost:11434')
OLLAMA_MODEL  = os.getenv('OLLAMA_MODEL', 'kullm:12b-instruct-q4_0')
```

---

## DB 연결 방식

```python
from dotenv import load_dotenv
import psycopg2, os

load_dotenv('.env')  # 프로젝트 루트의 .env (VPC 접속 정보)

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    dbname=os.getenv('DB_NAME'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD')
)
```

---

## 🗄️ DB 접근 코드 작성 원칙 (MANDATORY — VPC 네트워크 I/O 최소화)

> VPC PostgreSQL은 원격 서버다. 쿼리 1회당 네트워크 왕복이 발생한다.
> 루프 안에 DB 쿼리를 넣으면 수백~수천 번 왕복이 생겨 파이프라인이 치명적으로 느려진다.
> **코드 작성 전 반드시 DB 왕복 수를 계획하고 주석으로 명시한다.**

### ❌ 금지 패턴 — N+1 쿼리 (루프 안 DB 쿼리)

```python
# 절대 금지: 루프 안에서 fetch
for user_id in user_ids:                                      # 유저 수만큼
    cur.execute("SELECT ... WHERE user_id = %s", (user_id,))  # 왕복 발생!
    rows = cur.fetchall()
    cur.execute("INSERT INTO ... VALUES (%s)", (...))          # 왕복 발생!
```

### ✅ 올바른 패턴 — 전체 dump → Python 계산 → 배치 INSERT

```python
# DB 왕복 계획: 읽기 N회 + INSERT ~수십 회 = 총 ~수십 회

# 1. 루프 밖에서 전체 데이터를 한 번에 dump (DB 쿼리 1회)
cur.execute("SELECT user_id, col1, col2 FROM table WHERE ...")
all_data = {row[0]: row for row in cur.fetchall()}

# 2. 순수 Python 계산 (DB 왕복 없음)
results = []
for user_id in user_ids:
    results.append(compute(all_data.get(user_id)))

# 3. 배치 INSERT — 행 단위 INSERT 절대 금지, 10,000행 단위 배치
BATCH = 10_000
for i in range(0, len(results), BATCH):
    batch = results[i:i + BATCH]
    args = ",".join(cur.mogrify("(%s,%s)", r).decode() for r in batch)
    cur.execute(f"INSERT INTO target VALUES {args} ON CONFLICT ...")
    conn.commit()
```

### 구현 전 DB 왕복 수 계획표 작성 (필수)

코드 작성 전 아래 형식의 주석을 함수 docstring에 포함한다:

```python
"""
DB 왕복 계획:
  읽기: candidates dump (1회) + preferences dump (1회) + vod_tag dump (1회)
  쓰기: INSERT 배치 (~25회, 10,000행 단위)
  총계: ~28회  ← 100회 이상이면 설계 재검토
"""
```

### 설계 판단 기준

| 총 DB 왕복 수 | 판단 | 조치 |
|--------------|------|------|
| ~50회 이하 | ✅ 양호 | 그대로 구현 |
| 50~100회 | ⚠️ 주의 | 추가 dump 통합 검토 |
| 100회 초과 | ❌ 재설계 | 루프 안 쿼리 제거 필수 |

---

## 구현 완료 후 자가 점검

- [ ] 하드코딩된 API 키, IP, 비밀번호 없음
- [ ] 외부 API 호출마다 try-except + 폴백 처리
- [ ] Rate Limit: requests 간 sleep(0.5) 적용
- [ ] `WHERE {column} IS NULL` 조건으로 기존 값 보호
- [ ] 체크포인트 로직으로 중단 후 재시작 가능
- [ ] **루프 안에 `cur.execute` + `fetchall()` 없음 (N+1 쿼리 없음)**
- [ ] **INSERT는 행 단위가 아닌 배치 (mogrify 또는 execute_values)**
- [ ] **DB 왕복 계획표를 docstring에 명시함**
