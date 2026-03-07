# VOD 추천 시스템 - Database 개발 마스터 플랜

**프로젝트**: VOD 추천 시스템 PostgreSQL 데이터베이스
**브랜치**: Database_Design
**작성일**: 2026-03-06
**상태**: 개발 시작 전

---

## 1. 실제 데이터 규모 (설계요구사항.md 기준)

| 항목 | 수치 |
|------|------|
| 수집 기간 | 2025-01-01 ~ 2025-01-31 |
| 총 시청 이력 | 3,992,530건 |
| 고유 사용자 | 242,702명 |
| 고유 VOD | 166,159개 |
| 사용자당 평균 시청 수 | 16.45건 |
| VOD당 평균 시청 수 | 24.03건 |
| 평균 완주율 | 46.76% |
| 평균 만족도 | 0.443 |

---

## 2. 개발 단계 (Phases)

```
Phase 1: 핵심 스키마 DDL 작성        [PLAN_01_SCHEMA_DDL.md]
Phase 2: 데이터 마이그레이션          [PLAN_02_DATA_MIGRATION.md]
Phase 3: 성능 검증                   [PLAN_03_PERFORMANCE_TEST.md]
Phase 4: 확장 테이블 설계             [PLAN_04_EXTENSION_TABLES.md]
Phase 5: RAG 연동 DB 설계            [PLAN_05_RAG_DB_INTEGRATION.md]
```

---

## 3. 최종 산출물 목록

### Phase 1 산출물
```
Database_Design/schema/
├── create_tables.sql       # USER, VOD, WATCH_HISTORY DDL
├── create_indexes.sql      # 인덱스 생성
├── create_constraints.sql  # 제약조건
└── DESIGN.md               # 설계 근거 문서
```

### Phase 2 산출물
```
Database_Design/migration/
├── migrate.py              # Python 마이그레이션 스크립트
├── validate_data.py        # 데이터 검증 스크립트
└── migration_log.md        # 마이그레이션 결과 기록
```

### Phase 3 산출물
```
Database_Design/tests/
├── performance_test.sql    # 성능 테스트 쿼리
└── test_results.md         # 테스트 결과
```

### Phase 4 산출물
```
Database_Design/schema/
├── create_embedding_tables.sql     # VOD_EMBEDDING, USER_EMBEDDING
└── create_recommendation_table.sql # VOD_RECOMMENDATION
```

---

## 4. 기술 스택 결정사항

| 항목 | 결정 | 근거 |
|------|------|------|
| 주 데이터베이스 | PostgreSQL | 요구사항 명시 |
| 벡터 저장소 | Milvus | 별도 팀에서 처리 |
| ORM/마이그레이션 | SQLAlchemy (Python) | 요구사항 선택사항 |
| 파티셔닝 | RANGE (strt_dt 기준 연도) | 시계열 조회 최적화 |
| 실행 환경 | Docker (VPC) | 팀원 공유 PostgreSQL 협업 환경 |
| 접속 정보 관리 | `.env` 파일 (Git 제외) | 보안을 위해 팀 내 별도 공유 |

---

## 5. 핵심 설계 원칙

1. **정규화**: 최소 3NF - 각 테이블 정규화 단계 문서화 필수
2. **PostgreSQL 문법 준수**: 논리 스키마(MySQL)를 PostgreSQL로 변환
3. **NULL 허용 컬럼**: director, smry 등 RAG 처리 예정 컬럼은 NULL 허용
4. **RAG 추적 컬럼 추가**: rag_processed, rag_source, rag_processed_at
5. **만족도**: 베이지안 스코어 공식 `(v*R + m*C) / (v+m)`, m=5.0

---

## 6. MySQL → PostgreSQL 주요 변환 사항

논리 스키마(VOD_RECOMMENDATION_LOGICAL_SCHEMA.md)가 MySQL 문법으로 작성되어 있으므로 DDL 작성 시 아래 변환 적용:

| MySQL | PostgreSQL |
|-------|-----------|
| `AUTO_INCREMENT` | `BIGSERIAL` 또는 `GENERATED ALWAYS AS IDENTITY` |
| `ENGINE=InnoDB` | 제거 (PostgreSQL 기본) |
| `DEFAULT CHARSET=utf8mb4` | 제거 (PostgreSQL은 DB 레벨 설정) |
| `ON UPDATE CURRENT_TIMESTAMP` | 트리거로 구현 |
| `FULLTEXT INDEX` | `GIN` 인덱스 + `tsvector` |
| `GENERATED ALWAYS AS (subquery)` | 일반 컬럼 + 트리거 또는 뷰로 구현 |
| `JSON` 타입 | `JSONB` (PostgreSQL 권장) |
| `BOOLEAN` | `BOOLEAN` (동일) |
| `FLOAT` | `REAL` 또는 `DOUBLE PRECISION` |
| `LIMIT` | `LIMIT` (동일) |
| `DATE_SUB(NOW(), INTERVAL 30 DAY)` | `NOW() - INTERVAL '30 days'` |

---

## 7. 성능 목표

| 조회 패턴 | 목표 응답시간 |
|-----------|------------|
| 사용자별 시청이력 조회 (WHERE user_id = ?) | < 100ms |
| VOD별 시청 통계 조회 (WHERE vod_id = ?) | < 100ms |
| 날짜 범위 조회 (BETWEEN) | < 500ms |
| 만족도 상위 VOD 조회 (ORDER BY satisfaction DESC) | < 500ms |

---

## 8. 진행 체크리스트

- [x] Phase 1: 핵심 스키마 DDL 작성
  - [x] PLAN_01 검토
  - [x] create_tables.sql 작성
  - [x] create_indexes.sql 작성
  - [x] DESIGN.md 작성
- [x] Phase 2: 데이터 마이그레이션
  - [x] PLAN_02 검토
  - [x] migrate.py 작성
  - [x] VPC DB 연결 테스트 (환경변수 확인)
  - [x] 데이터 검증 (test_migration_db.sql T01~T12 전체 PASS, 2026-03-07)
- [x] Phase 3: 성능 테스트
  - [x] PLAN_03 검토
  - [x] performance_test.sql 작성
  - [x] EXPLAIN ANALYZE 실행 및 결과 기록 (P05 PASS, P01~P04/P06 VPC 환경 한계)
  - [x] VPC 설정 최적화 실험 6회 (최종: 1GB/32MB/0workers), 최고기록: P02 warm=1,714ms(-93%), P03 warm=17,984ms
- [ ] Phase 4: 확장 테이블
  - [ ] PLAN_04 검토
  - [ ] 임베딩/추천 테이블 DDL 작성
- [ ] Phase 5: RAG 연동
  - [ ] PLAN_05 검토
  - [ ] RAG 처리 후 DB 업데이트 로직 설계

---

**참고 문서**:
- [논리적 스키마](../skills/VOD_RECOMMENDATION_LOGICAL_SCHEMA.md)
- [만족도 공식](../skills/SATISFACTION_FORMULA_UPDATE.md)
- [프로젝트 가이드라인](../.claude/claude_md.md)
