# Orchestrator Agent 지시사항

## 역할
Phase별 TDD 사이클 전체를 관리한다. PLAN 파일을 읽고 작업을 분해하여 각 에이전트를 순서대로 호출하고, 완료 기준을 판단한다.

---

## 실행 순서

```
1. 해당 Phase의 PLAN 파일 읽기
2. 작업 목록 분해 (테스트 가능한 단위로)
3. Test Writer Agent 호출 → 테스트 파일 생성 확인
4. Developer Agent 호출 → 구현 파일 생성 확인
5. Test Writer Agent 재호출 → 테스트 실행 및 결과 수집
6. 결과 판단
   - 모든 테스트 PASS → Refactor Agent 호출
   - FAIL 존재 → Developer Agent 재호출 (최대 3회 반복)
7. Reporter Agent 호출 → 보고서 생성 확인
8. 완료 기준 체크
```

---

## Phase별 PLAN 파일 위치

| Phase | PLAN 파일 |
|-------|----------|
| Phase 1 | `Database_Design/plans/PLAN_01_SCHEMA_DDL.md` |
| Phase 2 | `Database_Design/plans/PLAN_02_DATA_MIGRATION.md` |
| Phase 3 | `Database_Design/plans/PLAN_03_PERFORMANCE_TEST.md` |
| Phase 4 | `Database_Design/plans/PLAN_04_EXTENSION_TABLES.md` |
| Phase 5 | `Database_Design/plans/PLAN_05_RAG_DB_INTEGRATION.md` |

---

## 작업 분해 원칙

- 테스트 가능한 최소 단위로 분해한다
- 각 단위는 독립적으로 검증 가능해야 한다
- FK 의존성이 있는 경우 순서를 반드시 지킨다 (user → vod → watch_history)

---

## 에이전트 호출 시 전달해야 할 정보

각 에이전트 호출 시 아래 정보를 반드시 포함한다:
- 현재 Phase 번호
- 작업 대상 파일 경로
- 이전 단계 결과 (Developer 호출 시 테스트 결과, Refactor 호출 시 구현 결과)

---

## 실패 처리 규칙

- Developer Agent가 3회 반복 후에도 FAIL이 남을 경우 → Reporter Agent에 실패 내용 전달 후 보고서 생성
- 보고서의 "오류 원인 분석" 및 "개선 방법" 섹션에 상세 기록
- 다음 Phase 진행 전 팀원 검토 권고

---

## 완료 기준 (Phase 공통)

- [ ] 테스트 파일 생성 완료
- [ ] 구현 파일 생성 완료
- [ ] 전체 테스트 PASS 또는 잔여 FAIL 사유 문서화 완료
- [ ] 보고서 생성 완료 (`Database_Design/reports/phaseX_report.md`)
