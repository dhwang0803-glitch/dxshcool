# Phase 2 결과 보고서

**Phase**: Phase 2 - 데이터 마이그레이션 (CSV → PostgreSQL)
**작성일**: 2026-03-07
**상태**: 단위 테스트 15/15 PASS, 통합 테스트 12/12 PASS — Phase 2 완료

---

## 1. 개발 결과

### 생성된 파일

| 파일 | 위치 | 설명 |
|------|------|------|
| migrate.py | Database_Design/migration/ | CSV → PostgreSQL 3개 테이블 적재 메인 스크립트 |
| validate_data.py | Database_Design/migration/ | 마이그레이션 전 CSV 사전 검증 스크립트 |
| test_migration_unit.py | Database_Design/tests/ | 데이터 변환 함수 단위 테스트 (T01~T15, 15건) |
| test_migration_db.sql | Database_Design/tests/ | 마이그레이션 완료 후 DB 통합 테스트 (T01~T12, 12건) |

### 주요 구현 내용

- **parse_disp_rtm**: `HH:MM` / `HH:MM:SS` 형식 문자열을 초 단위 정수로 변환. None / NaN / `-` 입력 시 0 반환
- **convert_nfx_use_yn**: NFX_USE_YN 컬럼의 `"Y"` → `True`, `"N"` → `False`, NaN → `None` 변환
- **clean_smry**: smry(줄거리) 컬럼에서 `-` 및 빈 문자열을 `None`(NULL)으로 정제
- **clip_completion_rate**: completion_rate 값을 0.0 ~ 1.0 범위로 클리핑 (초과분 강제 조정)
- **load_users**: user_table.csv 적재, 컬럼 소문자 변환 및 nfx_use_yn BOOLEAN 변환 후 `ON CONFLICT DO NOTHING`으로 삽입
- **load_vods**: vod_table.csv 적재, disp_rtm_sec 초 단위 변환·smry 정제·NaN→None 처리 후 삽입
- **load_watch_history**: watch_history_table.csv를 5,000건 배치 단위로 적재, **배치마다 새 DB 연결 생성**(VPC 타임아웃 방지), FK 위반 레코드는 건별 재시도 후 스킵·로그 기록
- **validate_counts**: 마이그레이션 완료 후 3개 테이블 건수를 기대값(user=242,702 / vod=166,159 / watch_history=3,992,530)과 비교 출력
- **validate_data.py**: CSV 적재 전 사전 검증 (중복 PK, FK 무결성, completion_rate 범위, NULL 현황, 데이터 건수 요약)
- **마이그레이션 로그**: `migration/migration.log` 파일에 실행 이력 및 경고 자동 기록
- **.env 기반 접속 관리**: DB 접속 정보를 `.env`에서 로드, Git 커밋 금지 원칙 준수

---

## 2. 테스트 결과

### 요약

| 구분 | 건수 |
|------|------|
| 단위 테스트 전체 | 15건 |
| 단위 테스트 PASS | 15건 |
| 단위 테스트 FAIL | 0건 |
| 단위 테스트 오류율 | 0% |
| 통합 테스트 전체 | 12건 |
| 통합 테스트 PASS | 12건 |
| 통합 테스트 FAIL | 0건 |
| 통합 테스트 오류율 | 0% |

- **실행 환경**: PostgreSQL 15.4 (VPC Docker)
- **단위 테스트 실행 파일**: `Database_Design/tests/test_migration_unit.py`
- **통합 테스트 실행 파일**: `Database_Design/tests/test_migration_db.sql`

### 단위 테스트 상세 결과 (test_migration_unit.py)

| 테스트 ID | 테스트 항목 | 결과 | 비고 |
|-----------|------------|------|------|
| T01 | parse_disp_rtm: `"01:21"` → 4860 (HH:MM 형식) | PASS | |
| T02 | parse_disp_rtm: `"00:29"` → 1740 (HH:MM 형식) | PASS | |
| T03 | parse_disp_rtm: `"01:30:00"` → 5400 (HH:MM:SS 형식) | PASS | |
| T04 | parse_disp_rtm: None / NaN → 0 (NULL 처리) | PASS | |
| T05 | parse_disp_rtm: `"-"` → 0 (대시 처리) | PASS | |
| T06 | convert_nfx_use_yn: `"Y"` → True | PASS | |
| T07 | convert_nfx_use_yn: `"N"` → False | PASS | |
| T08 | convert_nfx_use_yn: NaN → None | PASS | |
| T09 | clean_smry: `"-"` → None | PASS | |
| T10 | clean_smry: `""` (빈 문자열) → None | PASS | |
| T11 | clean_smry: 정상 텍스트 → 그대로 유지 | PASS | |
| T12 | clip_completion_rate: 0.8 → 0.8 (정상 범위 유지) | PASS | |
| T13 | clip_completion_rate: 1.5 → 1.0 (초과값 클리핑) | PASS | |
| T14 | clip_completion_rate: -0.1 → 0.0 (음수 클리핑) | PASS | |
| T15 | VPC DB 접속 확인 (.env 로드 및 SELECT 1) | PASS | |

### 통합 테스트 상세 결과 (test_migration_db.sql)

| 테스트 ID | 테스트 항목 | 기대값 | 결과 |
|-----------|------------|--------|------|
| T01 | user 테이블 건수 검증 | 242,702건 | PASS (실제: 242,702건) |
| T02 | vod 테이블 건수 검증 | 166,159건 | PASS (실제: 166,159건) |
| T03 | watch_history 테이블 건수 검증 | 3,992,530건 | PASS (실제: 3,992,530건) |
| T04 | watch_history → user FK 무결성 (orphan 0건) | 0건 | PASS (orphan: 0건) |
| T05 | watch_history → vod FK 무결성 (orphan 0건) | 0건 | PASS (orphan: 0건) |
| T06 | completion_rate 범위 검증 (0~1 초과 0건) | 0건 | PASS (초과: 0건) |
| T07 | satisfaction 범위 검증 (0~1 초과 0건) | 0건 | PASS (초과: 0건) |
| T08 | use_tms 음수값 검증 (0건) | 0건 | PASS (음수: 0건) |
| T09 | user.nfx_use_yn BOOLEAN 변환 (NULL 0건) | 0건 | PASS (NULL: 0건) |
| T10 | vod.disp_rtm_sec > 0 비율 >= 95% | 95% 이상 | PASS (99.57% / 유효: 165,452건 / 전체: 166,159건) |
| T11 | satisfaction = 0 건수 (±5% 허용: 956,612~1,057,310건) | 1,006,961건 근사 | PASS (실제: 1,006,961건) |
| T12 | satisfaction > 0 건수 (±5% 허용: 2,836,290~3,134,848건) | 2,985,569건 근사 | PASS (실제: 2,985,569건) |

> 실행 환경: PostgreSQL 15.4 (VPC Docker), 실행일: 2026-03-07

---

## 3. 오류 원인 분석

### VPC 연결 타임아웃 (마이그레이션 중 발생)

- **증상**: watch_history 배치 250번째 (~2,500,000건) 에서 `psycopg2.OperationalError: server closed the connection unexpectedly` 발생
- **원인**: 단일 psycopg2 연결을 전체 watch_history 적재(약 33분) 동안 유지 → VPC(1core/4GB) 가 장시간 유휴 연결 종료
- **test_migration_db.sql T10 구문 오류**: `RAISE EXCEPTION/NOTICE`에서 `%%`(리터럴 %)를 파라미터 슬롯으로 잘못 사용 → `too many parameters specified for RAISE`

---

## 4. 개선 방법

- **migrate.py**: `load_watch_history(conn)` → `load_watch_history()` 로 변경, 배치마다 `get_connection()` / `conn.close()` 호출
- **BATCH_SIZE**: 10,000 → 5,000 으로 축소하여 VPC 부하 감소
- **test_migration_db.sql T10**: `RAISE EXCEPTION/NOTICE`의 `%%` → `%` 로 수정

---

## 5. 개선 내용 (실제 적용)

### 버그 수정

- `migrate.py`: 배치 단위 DB 재연결 로직 추가 (VPC 타임아웃 방지)
- `migrate.py`: BATCH_SIZE 10,000 → 5,000 축소
- `test_migration_db.sql`: T10 RAISE 구문 `%%` → `%` 수정

### 리팩토링

해당 없음

---

## 6. CSV 데이터 적재 절차 (통합 테스트 실행을 위한 다음 단계)

통합 테스트(test_migration_db.sql) 실행을 위해서는 아래 절차를 순서대로 수행해야 합니다.

### Step 1: CSV 파일 VPC 업로드 (담당자 1명)

CSV 파일 업로드는 팀 내 1명이 담당하며, 이후 팀원 전원은 `.env`를 통해 VPC DB에 직접 접속합니다 (CSV 재업로드 불필요).

```bash
# CSV 파일을 VPC 서버로 업로드 (scp)
scp -r ./data user@<VPC_IP>:/home/user/vod_data/
```

적재 순서는 FK 의존성을 고려하여 아래 순서를 반드시 준수합니다.

| 순서 | 파일 | 테이블 | 예상 건수 | 비고 |
|------|------|--------|----------|------|
| 1 | user_table.csv | user | 242,702건 | 독립 테이블 |
| 2 | vod_table.csv | vod | 166,159건 | 독립 테이블 |
| 3 | watch_history_table.csv | watch_history | 3,992,530건 | user + vod 참조 (FK) |

> watch_history는 user 및 vod 테이블이 먼저 적재된 이후에만 업로드 가능합니다.

### Step 2: validate_data.py 실행 (마이그레이션 전 CSV 사전 검증)

```bash
cd Database_Design/migration
python validate_data.py
```

validate_data.py는 다음 항목을 검사합니다.
- USER / VOD PK 중복 확인
- WATCH_HISTORY → USER / VOD FK 무결성 사전 확인
- completion_rate 범위 이상값 탐지 (클리핑 대상 사전 파악)
- director / smry NULL 현황 출력
- 데이터 건수 요약 (기대값과 비교)

모든 검증 통과 메시지 확인 후 다음 단계를 진행합니다.

### Step 3: migrate.py 실행 (PostgreSQL 적재)

```bash
cd Database_Design/migration
python migrate.py
```

- `.env` 파일에서 DB 접속 정보 자동 로드
- user → vod → watch_history 순으로 적재
- watch_history는 10,000건 배치 단위 처리
- FK 위반 레코드는 건별 재시도 후 스킵 및 `migration.log`에 기록
- 완료 후 3개 테이블 건수 자동 검증 출력

### Step 4: test_migration_db.sql 실행 (통합 테스트)

```bash
psql -U <user> -d vod_db -f Database_Design/tests/test_migration_db.sql
```

- 모든 DO 블록에서 RAISE EXCEPTION 없이 완료되면 통합 테스트 PASS
- T01~T12 전 항목 PASS 확인 후 Phase 2 완전 완료로 처리

---

## 7. 다음 Phase 권고사항

- **Phase 3 진행 조건**: 통합 테스트(test_migration_db.sql) T01~T12 전체 PASS 확인 후 Phase 3로 진입할 것
- **CSV 적재 전 .env 파일 준비**: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` 5개 항목이 반드시 설정되어 있어야 하며, `.gitignore`에 `.env`가 포함되어 있는지 사전 확인 필요
- **watch_history 적재 시간 고려**: 3,992,530건을 10,000건 배치로 처리하므로 약 400회 이상 반복 실행됨. 충분한 실행 시간과 VPC 세션 유지 조건 확보 필요
- **대용량 적재 최적화 옵션**: 초기 적재 속도가 느릴 경우 PLAN_02에 정의된 `COPY FROM STDIN` 방식 또는 인덱스 사후 생성(`CREATE INDEX CONCURRENTLY`) 전략 적용 검토
- **migration.log 보관**: 적재 완료 후 `migration/migration.log` 파일에 FK 위반 스킵 건수가 기록되므로, Phase 3 진입 전 로그를 검토하여 orphan 데이터 규모를 파악할 것
- **Phase 3 참조 파일**: `Database_Design/plans/PLAN_03_PERFORMANCE_TEST.md`
