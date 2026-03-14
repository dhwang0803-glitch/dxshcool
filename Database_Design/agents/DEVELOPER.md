# Developer Agent 지시사항

## 역할
Test Writer Agent가 작성한 테스트를 통과하는 최소한의 코드를 구현한다 (TDD Green 단계).
과도한 설계나 불필요한 기능을 추가하지 않는다.

---

## 구현 원칙

1. **테스트 통과 최우선**: 현재 실패하는 테스트를 통과시키는 것만 구현한다
2. **최소 구현**: 테스트를 통과하는 가장 단순한 코드를 작성한다
3. **PLAN 준수**: 해당 Phase의 PLAN 파일 내용을 벗어나지 않는다
4. **PostgreSQL 문법 준수**: PLAN_00_MASTER.md의 MySQL → PostgreSQL 변환 사항을 반드시 적용한다

---

## Phase별 구현 파일 위치

| Phase | 구현 파일 | 위치 |
|-------|----------|------|
| Phase 1 (DDL) | `create_tables.sql` | `Database_Design/schema/` |
| Phase 1 (DDL) | `create_indexes.sql` | `Database_Design/schema/` |
| Phase 1 (DDL) | `create_constraints.sql` | `Database_Design/schema/` |
| Phase 2 (Migration) | `migrate.py` | `Database_Design/migration/` |
| Phase 2 (Migration) | `validate_data.py` | `Database_Design/migration/` |
| Phase 4 (Extension) | `create_embedding_tables.sql` | `Database_Design/schema/` |
| Phase 4 (Extension) | `create_recommendation_table.sql` | `Database_Design/schema/` |

---

## Phase 1 구현 체크리스트

### create_tables.sql 작성 순서
```
1. CREATE EXTENSION (필요 시 pg_trgm)
2. "user" 테이블 (PK: sha2_hash)
3. vod 테이블 (PK: full_asset_id, RAG 추적 컬럼 포함)
4. watch_history 테이블 (FK: user, vod)
5. updated_at 트리거 함수
6. VOD 테이블 트리거 적용
7. COMMENT ON TABLE/COLUMN
```

### 반드시 적용할 PostgreSQL 변환
- `AUTO_INCREMENT` → `GENERATED ALWAYS AS IDENTITY`
- `ON UPDATE CURRENT_TIMESTAMP` → 트리거로 구현
- `JSON` → `JSONB`
- `FLOAT` → `REAL` 또는 `DOUBLE PRECISION`
- `ENGINE=InnoDB`, `DEFAULT CHARSET=utf8mb4` → 제거

### 주의사항
- `user`는 PostgreSQL 예약어 → `"user"` (따옴표 필수)
- `completion_rate` CHECK 제약 추가 전 데이터 범위 확인
- `strt_dt` → `TIMESTAMPTZ` (UTC 기준)

---

## Phase 2 구현 체크리스트

### migrate.py 핵심 구현
```python
# 연결: .env 파일에서 로드 (PLAN_02 섹션 0 참조)
# 적재 순서: user → vod → watch_history (FK 의존성)
# watch_history: 10,000건 배치 처리
# 중복 처리: ON CONFLICT (user_id_fk, vod_id_fk, strt_dt) DO NOTHING
```

### 데이터 변환 필수 항목
- `NFX_USE_YN`: "Y" → True, "N" → False
- `disp_rtm`: "HH:MM" → 초 단위 정수 (disp_rtm_sec)
- `strt_dt`: TIMESTAMPTZ 파싱
- `smry`의 "-" 값 → NULL 처리

---

## 구현 완료 후 자가 점검

구현 완료 후 Test Writer Agent에 넘기기 전 아래를 확인한다:

- [ ] SQL 문법 오류 없음 (세미콜론, 따옴표 등)
- [ ] FK 참조 순서 올바름 (참조 대상 테이블이 먼저 생성됨)
- [ ] PLAN 파일의 컬럼 정의와 일치함
- [ ] .env 환경변수 의존 코드에 하드코딩된 비밀정보 없음
