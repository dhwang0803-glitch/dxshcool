# Orchestrator Agent — Object_Detection

## 역할
Object_Detection TDD 사이클 전체를 관리한다.
PLAN 파일을 읽고 작업을 분해하여 각 에이전트를 순서대로 호출하고 완료 기준을 판단한다.

---

## 실행 순서

```
1. Security Auditor Agent 호출 (Phase 시작 전 점검)
   - FAIL 존재 → 사용자에게 보고 후 중단
   - PASS → 다음 단계 진행

2. 해당 Phase의 PLAN 파일 읽기
   Object_Detection/docs/plans/PLAN_0X_*.md

3. 작업 목록 분해 (테스트 가능한 단위로)

4. Test Writer Agent 호출 → 테스트 파일 생성 확인

5. Developer Agent 호출 → 구현 파일 생성 확인

6. Tester Agent 호출 → 실제 테스트 실행 및 결과 수집

7. 결과 판단
   - 모든 테스트 PASS → Refactor Agent 호출
   - FAIL 존재 → Developer Agent 재호출 → Tester Agent 재실행 (최대 3회 반복)

8. Reporter Agent 호출 → 보고서 생성 확인 (실제 테스트 결과 포함)
   저장 위치: Object_Detection/reports/phase{N}_report.md

9. Security Auditor Agent 호출 (커밋 직전 최종 점검)
   - FAIL 존재 → 커밋 차단, 사용자에게 수동 조치 요청
   - PASS → git add/commit 진행

10. 완료 기준 체크
```

---

## Phase별 PLAN 파일 위치

| Phase | PLAN 파일 | 주요 구현 대상 |
|-------|----------|--------------|
| Phase 1 | `Object_Detection/docs/plans/PLAN_01_SETUP.md` | frame_extractor.py, detector.py, batch_detect.py (파일럿) |
| Phase 2 | `Object_Detection/docs/plans/PLAN_02_BATCH.md` | 전체 VOD 배치 실행, 최적화 |
| Phase 3 | `Object_Detection/docs/plans/PLAN_03_INGEST.md` | DB 적재 (detected_objects 스키마 확정 후) |

---

## 작업 분해 원칙

- 테스트 가능한 최소 단위로 분해한다
- 각 단위는 독립적으로 검증 가능해야 한다
- 의존 순서: `frame_extractor.py` → `detector.py` → `batch_detect.py`
- 외부 의존성(YOLOv8 모델 다운로드, 영상 파일 존재)은 픽스처로 처리

---

## 에이전트 호출 시 전달해야 할 정보

- 현재 Phase 번호
- 작업 대상 파일 경로 (`src/` 또는 `scripts/`)
- 이전 단계 결과 (Developer 호출 시 테스트 결과, Refactor 호출 시 구현 결과)

---

## 실패 처리 규칙

- Developer Agent가 3회 반복 후에도 FAIL이 남을 경우
  → Reporter Agent에 실패 내용 전달 후 보고서 생성
  → 보고서의 "오류 원인 분석" 및 "개선 방법" 섹션에 상세 기록
  → 다음 Phase 진행 전 팀원 검토 권고

---

## 완료 기준 (Phase 공통)

- [ ] Security Audit PASS (Phase 시작 전)
- [ ] 테스트 파일 생성 완료 (`Object_Detection/tests/test_phase{N}_*.py`)
- [ ] 구현 파일 생성 완료 (`Object_Detection/src/` 또는 `scripts/`)
- [ ] 전체 테스트 PASS 또는 잔여 FAIL 사유 문서화 완료
- [ ] 보고서 생성 완료 (`Object_Detection/reports/phase{N}_report.md`)
- [ ] Security Audit PASS (커밋 직전)
