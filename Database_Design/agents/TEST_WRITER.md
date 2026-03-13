# Test Writer Agent 지시사항

## 역할
구현 전에 실패하는 테스트를 먼저 작성한다 (TDD Red 단계).
구현 후에는 테스트를 실행하고 결과를 수집한다 (검증 단계).

---

## 테스트 작성 원칙

1. 구현 코드가 없어도 테스트를 먼저 작성한다
2. 각 테스트는 하나의 요구사항만 검증한다
3. 기대값을 명확하게 명시한다 (예: `기대값: 600,000건`)
4. 테스트 실패 시 원인을 파악할 수 있는 메시지를 포함한다

---

## Phase별 테스트 파일 위치 및 형식

| Phase | 테스트 파일 | 형식 |
|-------|-----------|------|
| Phase 1 (DDL) | `Database_Design/tests/test_schema.sql` | SQL |
| Phase 2 (Migration) | `Database_Design/tests/test_migration.py` | Python |
| Phase 3 (Performance) | `Database_Design/tests/test_performance.sql` | SQL |
| Phase 4 (Extension) | `Database_Design/tests/test_extension.sql` | SQL |
| Phase 5 (RAG) | `Database_Design/tests/test_rag_integration.py` | Python |

---

## SQL 테스트 작성 형식

```sql
-- =============================================================
-- 테스트: [테스트 항목명]
-- 목적: [무엇을 검증하는지]
-- 기대값: [예상 결과]
-- =============================================================

-- [테스트 쿼리]
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM [테이블명];
    IF v_count <> [기대값] THEN
        RAISE EXCEPTION '테스트 실패: 기대값 %, 실제값 %', [기대값], v_count;
    END IF;
    RAISE NOTICE '테스트 통과: [테스트 항목명]';
END $$;
```

---

## Python 테스트 작성 형식

```python
import pytest
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()

@pytest.fixture
def conn():
    connection = psycopg2.connect(
        host=os.getenv('DB_HOST'),
        port=os.getenv('DB_PORT'),
        dbname=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )
    yield connection
    connection.close()

def test_[항목명](conn):
    """[테스트 목적 설명]"""
    cursor = conn.cursor()
    cursor.execute("[검증 쿼리]")
    result = cursor.fetchone()[0]
    assert result == [기대값], f"기대값: {[기대값]}, 실제값: {result}"
```

---

## Phase 1 (DDL) 필수 테스트 항목

### 테이블 존재 확인
- `user` 테이블 존재
- `vod` 테이블 존재
- `watch_history` 테이블 존재

### 컬럼 및 타입 확인
- `user.sha2_hash` → VARCHAR(64), PK
- `vod.full_asset_id` → VARCHAR(64), PK
- `watch_history.watch_history_id` → BIGINT, IDENTITY
- `watch_history.user_id_fk` → FK → user.sha2_hash
- `watch_history.vod_id_fk` → FK → vod.full_asset_id

### 제약조건 확인
- `watch_history` UNIQUE (user_id_fk, vod_id_fk, strt_dt)
- `watch_history.use_tms` CHECK (>= 0)
- `watch_history.completion_rate` CHECK (0 ~ 1)
- `watch_history.satisfaction` CHECK (0 ~ 1)

### 인덱스 존재 확인
- `idx_wh_user_id`, `idx_wh_vod_id`, `idx_wh_strt_dt`
- `idx_wh_satisfaction`, `idx_wh_user_strt`

### 트리거 확인
- `trg_vod_updated_at` 존재 및 동작

---

## Phase 2 (Migration) 필수 테스트 항목

### 건수 검증
- `user` 테이블: 600,000건
- `vod` 테이블: 실제 CSV 건수와 일치
- `watch_history` 테이블: 44,000,000건

### FK 무결성 검증
- `watch_history` → `user` orphan 레코드 0건
- `watch_history` → `vod` orphan 레코드 0건

### 데이터 품질 검증
- `completion_rate` 범위: 0 ~ 1
- `satisfaction` 범위: 0 ~ 1
- `nfx_use_yn` NULL 없음 (BOOLEAN 변환 완료)

---

## 테스트 결과 수집 형식

테스트 실행 후 아래 형식으로 결과를 정리하여 Reporter Agent에 전달한다:

```
전체 테스트: X건
PASS: X건
FAIL: X건
오류율: X%

FAIL 목록:
- [테스트명]: [실패 메시지]
```
