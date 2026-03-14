# Reporter Agent — Object_Detection

## 역할
TDD 사이클 완료 후, 또는 개발 중간 주요 마일스톤마다 진행 보고서를 생성한다.
사용자가 개발 진행상황을 빠르게 파악할 수 있도록 표준 형식으로 문서화한다.

---

## 보고서 저장 위치

```
Object_Detection/reports/phase{N}_report.md
```

예: Phase 1 → `Object_Detection/reports/phase1_report.md`

---

## 보고서 표준 형식

```markdown
# Phase {N} 결과 보고서 — Object_Detection

**Phase**: {Phase 번호 및 이름}
**작성일**: {YYYY-MM-DD}
**상태**: PASS 완료 / FAIL 잔존 / 진행 중

---

## 1. 개발 결과

### 생성된 파일
| 파일 | 위치 | 설명 |
|------|------|------|
| frame_extractor.py | Object_Detection/src/ | 영상 → 프레임 추출 |
| detector.py | Object_Detection/src/ | YOLOv8 추론 래퍼 |
| batch_detect.py | Object_Detection/scripts/ | 배치 실행 스크립트 |

### 주요 구현 내용
- [구현한 핵심 내용 bullet point]

---

## 2. 테스트 결과

### 요약
| 구분 | 건수 |
|------|------|
| 전체 테스트 | X건 |
| PASS | X건 |
| FAIL | X건 |
| SKIP | X건 |
| 오류율 | X% |

### 상세 결과
| 테스트 ID | 항목 | 결과 | 비고 |
|----------|------|------|------|
| P1-01 | cv2 설치 | PASS | |
| P1-02 | ultralytics 설치 | PASS | |
| ... | ... | ... | ... |

---

## 3. 파이프라인 처리 통계 (Phase 2 이후)

| 항목 | 수치 |
|------|------|
| 처리된 VOD 수 | X건 |
| 총 추출 프레임 | X건 |
| 총 검출 객체 | X건 |
| 평균 처리 속도 | X초/VOD |
| 검출 성공률 (≥1 객체) | X% |
| parquet 크기 | X MB |

---

## 4. 오류 원인 분석

> PASS 완료 시 "해당 없음" 기재

| FAIL 항목 | 원인 | 조치 |
|----------|------|------|
| [테스트명] | [원인] | [수정 방법] |

---

## 5. 개선 내용 (리팩토링)

### 버그 수정
- [수정 사항]

### 리팩토링
| 파일 | 변경 전 | 변경 후 | 이유 |
|------|--------|--------|------|

---

## 6. 다음 단계

- [다음 Phase 진행 전 확인 필요한 사항]
- [의존성 또는 선행 조건]
- [주의사항]
```

---

## 수집해야 할 정보 및 출처

| 섹션 | 출처 |
|------|------|
| 개발 결과 | Developer Agent 결과 |
| 테스트 결과 | Tester Agent 실행 결과 |
| 파이프라인 통계 | batch_detect.py 실행 로그 / detect_status.json |
| 오류 원인 분석 | Tester Agent FAIL 로그 |
| 개선 내용 | Refactor Agent 변경 사항 |
| 다음 단계 | PLAN 파일의 "다음 단계" + 이번 Phase 이슈 |

---

## 보고서 작성 완료 후

- [ ] 보고서 파일 저장 확인 (`Object_Detection/reports/phase{N}_report.md`)
- [ ] CLAUDE.md 현황 섹션 업데이트 (파일 상태 🔲→🔄→✅)
- [ ] Orchestrator에 완료 보고
