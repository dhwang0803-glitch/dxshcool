# Phase 4: MEDIUM 우선순위 처리 (선택)

**단계**: Phase 4 / 4 (선택)
**목표**: cast_guest / smry 결측 20,000건 처리
**산출물**: `reports/phase4_report.md`
**선행 조건**: Phase 3 완료, 팀 승인 (MEDIUM은 선택적 처리)

---

## 1. 처리 대상

| 컬럼 | 결측 건수 | 성공률 예상 | 비고 |
|------|----------|-----------|------|
| cast_guest | 18,000개 | 85% | 조연 배우, 정확도 낮음 |
| smry | 2,000개 | 80% | 줄거리 생성, LLM 의존도 높음 |

---

## 2. 구현 전략

### cast_guest
- IMDB API → Supporting cast 항목 추출
- 최대 5명 제한 (주연과 중복 제거)
- 신뢰도 임계값: `confidence ≥ 0.55` (MEDIUM이므로 낮게)

### smry (줄거리)
- Wikipedia 줄거리 섹션 크롤링 → Kullm으로 한국어 200자 요약
- 기존 smry에 "-" (대시) 값만 대상
- 신뢰도 임계값: `confidence ≥ 0.60`

---

## 3. 테스트 항목 (tests/test_phase4_medium.py)

| ID | 항목 | 기대값 |
|----|------|--------|
| P4-01 | cast_guest 검색 (기생충) | 1명 이상 non-NULL |
| P4-02 | cast_guest 중복 제거 (cast_lead와 중복 없음) | True |
| P4-03 | smry 생성 (기생충) | 50자 이상 한국어 텍스트 |
| P4-04 | smry 최대 길이 제한 (500자) | len(smry) ≤ 500 |
| P4-05 | cast_guest 채움률 | ≥ 80% |
| P4-06 | smry 채움률 | ≥ 75% |

---

**이전 단계**: PLAN_03_QUALITY_MONITORING.md
