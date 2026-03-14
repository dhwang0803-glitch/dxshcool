# Tester Agent 지시사항

## 역할
Developer Agent가 구현 파일을 작성한 후, VPC PostgreSQL에 직접 접속하여 테스트를 실행하고 결과를 수집한다.
사람이 개입하지 않고 자동으로 실행한다.

---

## 접속 정보 로드

`.env` 파일에서 접속 정보를 읽는다:

```bash
# .env 파일 위치
C:\Users\user\Documents\GitHub\vod_recommendation\.env

# 환경변수 파싱 및 접속 테스트
export $(grep -v '^#' /c/Users/user/Documents/GitHub/vod_recommendation/.env | xargs)
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "SELECT version();"
```

접속 실패 시 Orchestrator에 즉시 보고하고 중단한다.

---

## Phase별 실행 순서

### Phase 1 (Schema DDL)
```bash
# 1. 테이블 생성
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schema/create_tables.sql

# 2. 인덱스 생성
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schema/create_indexes.sql

# 3. 테스트 실행
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/tests/test_schema.sql 2>&1
```

### Phase 2 (Migration)
```bash
# 1. 마이그레이션 실행 (Python)
cd /c/Users/user/Documents/GitHub/vod_recommendation
python Database_Design/migration/migrate.py

# 2. 테스트 실행
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/tests/test_migration.sql 2>&1
# 또는 pytest
python -m pytest Database_Design/tests/test_migration.py -v 2>&1
```

### Phase 3 (Performance)
```bash
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/tests/test_performance.sql 2>&1
```

### Phase 4 (Extension)
```bash
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schema/create_embedding_tables.sql

PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schema/create_recommendation_table.sql

PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/tests/test_extension.sql 2>&1
```

### Phase 5 (RAG Integration)
```bash
python -m pytest Database_Design/tests/test_rag_integration.py -v 2>&1
```

---

## 결과 파싱 규칙

### SQL 테스트 결과 파싱
출력에서 PASS/FAIL 건수를 집계한다:
```bash
# PASS 건수
echo "$output" | grep -c "\[T[0-9]* PASS\]"

# FAIL 건수
echo "$output" | grep -c "\[T[0-9]* FAIL\]"

# FAIL 항목 상세
echo "$output" | grep "\[T[0-9]* FAIL\]"
```

### Python 테스트 결과 파싱 (pytest)
```bash
# 마지막 요약 줄에서 PASS/FAIL 추출
echo "$output" | grep -E "passed|failed|error"
```

---

## 재실행 처리 (스키마 충돌 방지)

이미 테이블/인덱스가 존재하는 경우를 대비해 구현 파일에는 반드시 아래 패턴이 사용되어야 한다:
```sql
CREATE TABLE IF NOT EXISTS ...
CREATE INDEX IF NOT EXISTS ...
DROP TABLE IF EXISTS ... CASCADE  -- 재실행 시에만
```

재실행이 필요한 경우 (Developer 수정 후 재시도):
```bash
# 테이블 초기화 후 재실행
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c "
  DROP TABLE IF EXISTS watch_history CASCADE;
  DROP TABLE IF EXISTS vod CASCADE;
  DROP TABLE IF EXISTS \"user\" CASCADE;
"
# 이후 create_tables.sql, create_indexes.sql 순서로 재실행
```

---

## Orchestrator에 전달할 결과 형식

```
[Tester 실행 결과]
- 실행 환경: PostgreSQL X.X (VPC Docker)
- 실행 파일: [파일명 목록]
- 전체 테스트: X건
- PASS: X건
- FAIL: X건
- 오류율: X%

FAIL 항목:
- [T번호 FAIL] 메시지

다음 액션:
- FAIL 0건 → Refactor Agent 호출
- FAIL 존재 → Developer Agent 재호출 (재시도 N/3회)
```

---

## 주의사항

1. `.env` 파일의 접속 정보를 로그나 출력에 노출하지 않는다
2. 테스트 실행 중 생성된 임시 데이터는 테스트 파일 내에서 정리한다 (T60 트리거 테스트처럼)
3. VPC 연결 실패 시 재시도 없이 즉시 Orchestrator에 보고한다
4. 실행 경로는 항상 프로젝트 루트 기준 절대경로를 사용한다
