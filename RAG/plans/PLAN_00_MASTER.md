# RAG Pipeline - 마스터 계획

**프로젝트**: VOD 추천 시스템 - RAG 기반 메타데이터 결측치 채우기
**목표**: 로컬 LLM(Kullm-12B + Ollama) + 외부 소스(IMDB/Wikipedia/KMRB)를 활용해 73,000개 결측치 자동 채우기
**작성일**: 2026-03-08

---

## 아키텍처 결정 (확정)

```
[검색 소스]
  IMDB / Wikipedia / KMRB
       ↓ (컨텍스트 텍스트)
[로컬 LLM]
  Kullm-12B (Ollama, int4 양자화)
       ↓ (구조화 추출)
[검증]
  validation.py (형식 / 신뢰도)
       ↓
[VPC PostgreSQL]
  UPDATE vod SET director=..., rag_processed=TRUE, rag_source='IMDB'
```

### 벡터 DB 역할
- Chroma + KR-SBERT: 유사 VOD 컨텍스트 보강 (Retrieval 단계)
- pgvector (기존 vod_embedding): 수정 없음 (VOD_Embedding 브랜치 담당)

---

## 처리 대상

| 컬럼 | 결측 건수 | 우선순위 | 예상 성공률 |
|------|----------|---------|------------|
| director | 15,000개 | HIGH | 95% |
| cast_lead | 25,000개 | HIGH | 90% |
| rating | 5,000개 | HIGH | 98% |
| release_date | 8,000개 | HIGH | 95% |
| cast_guest | 18,000개 | MEDIUM | 85% |
| smry | 2,000개 | MEDIUM | 80% |
| **합계** | **~73,000개** | | |

---

## Phase 구성

| Phase | 내용 | PLAN 파일 | 산출물 |
|-------|------|----------|--------|
| Phase 1 | 환경 설정 + 파일럿 (100건) | PLAN_01_SETUP_PILOT.md | search_functions.py, validation.py, 파일럿 리포트 |
| Phase 2 | HIGH 우선순위 배치 처리 | PLAN_02_HIGH_PRIORITY.md | rag_pipeline.py, DB UPDATE (53K건) |
| Phase 3 | 품질 평가 & 모니터링 | PLAN_03_QUALITY_MONITORING.md | monitoring.py, quality_analysis.py, 최종 리포트 |
| Phase 4 (선택) | MEDIUM 우선순위 처리 | PLAN_04_MEDIUM_PRIORITY.md | DB UPDATE (20K건) |

---

## 파일 구조

```
RAG/
├── plans/
│   ├── PLAN_00_MASTER.md           ← 이 파일
│   ├── PLAN_01_SETUP_PILOT.md
│   ├── PLAN_02_HIGH_PRIORITY.md
│   ├── PLAN_03_QUALITY_MONITORING.md
│   └── PLAN_04_MEDIUM_PRIORITY.md
├── agents/
│   ├── ORCHESTRATOR.md
│   ├── DEVELOPER.md
│   ├── TEST_WRITER.md
│   ├── TESTER.md
│   ├── REFACTOR.md
│   ├── REPORTER.md
│   └── SECURITY_AUDITOR.md
├── skills/
│   ├── SKILL_01_LOCAL_LLM_SETUP.md
│   ├── SKILL_02_VECTOR_DB_FOR_RAG.md
│   ├── SKILL_03_LOCAL_RAG_PIPELINE.md
│   ├── SKILL_04_LOCAL_LLM_PROMPTING.md
│   └── SKILL_05_LOCAL_RAG_EVALUATION.md
├── src/
│   ├── search_functions.py         ← Phase 1 구현
│   ├── validation.py               ← Phase 1 구현
│   ├── rag_pipeline.py             ← Phase 2 구현
│   ├── monitoring.py               ← Phase 3 구현 (선택)
│   └── quality_analysis.py         ← Phase 3 구현 (선택)
├── tests/
│   ├── test_phase1_pilot.py        ← Phase 1 테스트
│   ├── test_phase2_high.py         ← Phase 2 테스트
│   └── test_phase3_quality.py      ← Phase 3 테스트
├── config/
│   ├── api_keys.env                ← API 키 (git 제외)
│   └── rag_config.yaml             ← 파이프라인 설정
├── reports/                        ← 단계별 리포트 저장
└── claude.md
```

---

## TDD 워크플로우 (전 Phase 공통)

```
Security Auditor (시작 전)
  ↓
PLAN 파일 읽기
  ↓
Test Writer → 테스트 먼저 작성 (Red)
  ↓
Developer → 최소 구현 (Green)
  ↓
Tester → 실제 실행 & 결과 수집
  ↓ (FAIL 시 최대 3회 반복)
Refactor → 코드 개선 (Refactor)
  ↓
Reporter → reports/ 에 리포트 저장
  ↓
Security Auditor (커밋 직전)
  ↓
git commit & push
```

---

## 환경 요구사항

| 항목 | 스펙 |
|------|------|
| Python | 3.10+ (myenv) |
| LLM | Kullm-12B (Ollama, int4) |
| 임베딩 | snunlp/KR-SBERT-V40K-klueNLI-augmented |
| 벡터 DB | Chroma (로컬) |
| DB | VPC PostgreSQL 15.4 + pgvector |
| API | IMDB API, Wikipedia API, KMRB (공개) |

---

## 성공 지표

| 지표 | 목표 |
|------|------|
| HIGH 우선순위 채움률 | ≥ 95% |
| 전체 정확도 (샘플 검증) | ≥ 90% |
| 신뢰도 점수 평균 | ≥ 0.90 |
| 처리 시간 (HIGH 53K) | ≤ 2주 |

---

## DB 마이그레이션 (vod 테이블 추적 컬럼 추가)

```sql
-- Phase 1 시작 전 VPC DB에 적용 (Database_Design 브랜치 협의 후)
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_processed     BOOLEAN   DEFAULT FALSE;
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_source        VARCHAR(50);
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_processed_at  TIMESTAMPTZ;
ALTER TABLE vod ADD COLUMN IF NOT EXISTS rag_confidence    REAL;
```

---

## 진행 체크리스트

- [ ] Phase 1: 환경 설정 + 파일럿 100건 완료
- [ ] Phase 2: HIGH 우선순위 53,000건 완료
- [ ] Phase 3: 품질 평가 및 최종 리포트 완료
- [ ] Phase 4 (선택): MEDIUM 우선순위 20,000건
