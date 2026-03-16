# Phase 2: HIGH 우선순위 배치 처리

**단계**: Phase 2 / 4
**목표**: director / cast_lead / rating / release_date 결측 53,000건 채우기 + vod 테이블 UPDATE
**산출물**: `src/rag_pipeline.py`, `reports/phase2_report.md`
**선행 조건**: Phase 1 완료 (파일럿 80% 이상 성공), Chroma 벡터 DB 구축 완료

---

## 1. 벡터 DB 구축 (Phase 2 시작 전 1회)

```python
# KR-SBERT + Chroma로 기존 VOD 메타데이터 인덱싱
# 기존 director/cast 값이 있는 VOD를 컨텍스트로 활용
# 대상: vod 테이블 전체 (~4백만 행 → 필드 있는 것만)
```

| 항목 | 값 |
|------|---|
| 임베딩 모델 | snunlp/KR-SBERT-V40K-klueNLI-augmented (768차원) |
| 벡터 DB | Chroma (로컬, `config/chroma_db/`) |
| 인덱싱 기준 | asset_nm + genre + CT_CL |
| 검색 시 k | 3개 유사 VOD |

---

## 2. rag_pipeline.py 구조

### RAGPipeline 클래스

```python
class RAGPipeline:
    def __init__(self, config_path):
        # Ollama LLM, Chroma, psycopg2 DB 연결 초기화

    def process_high_priority(self, batch_size=50, checkpoint_path=None):
        # director → cast_lead → rating → release_date 순서로 처리
        # 체크포인트: 중단 후 재시작 가능

    def _process_column(self, column, vods, batch_size):
        # 배치 처리 + 병렬 검색 (ThreadPoolExecutor)

    def _search_and_validate(self, vod, column):
        # search_functions → validate → confidence_score

    def update_database(self, results):
        # ON CONFLICT DO UPDATE, rag_processed=TRUE 기록

    def generate_report(self):
        # 처리 통계 → reports/phase2_report.md
```

### 처리 순서 (컬럼별 독립 배치)

```
director (15,000건)
  → Wikipedia/IMDB 검색 → Kullm 추출 → validate → DB UPDATE
  ↓ (병렬 가능)
cast_lead (25,000건)
  → IMDB 검색 → Kullm 추출 → validate → DB UPDATE
  ↓
rating (5,000건)
  → KMRB 검색 → validate → DB UPDATE (LLM 불필요, 규칙 기반)
  ↓
release_date (8,000건)
  → IMDB/Wikipedia → validate → DB UPDATE
```

---

## 3. DB UPDATE SQL

```sql
UPDATE vod SET
    director          = %(director)s,
    rag_processed     = TRUE,
    rag_source        = %(source)s,
    rag_processed_at  = NOW(),
    rag_confidence    = %(confidence)s
WHERE full_asset_id = %(full_asset_id)s
  AND director IS NULL;   -- 기존 값 보호
```

---

## 4. 체크포인트 전략

```python
# 처리 완료 vod_id를 checkpoint.json에 저장
# 재시작 시 이미 처리된 항목 건너뜀
# 배치 50건마다 체크포인트 갱신
```

---

## 5. 테스트 항목 (tests/test_phase2_high.py)

| ID | 항목 | 기대값 |
|----|------|--------|
| P2-01 | RAGPipeline 초기화 (LLM/Chroma/DB 연결) | 예외 없음 |
| P2-02 | _process_column("director", 샘플 10건) | 8건 이상 non-NULL |
| P2-03 | 배치 처리 (50건) 완료 | 체크포인트 파일 생성 |
| P2-04 | 체크포인트 재시작 | 중복 처리 0건 |
| P2-05 | update_database 실행 후 vod 확인 | rag_processed=TRUE |
| P2-06 | 기존 director 값 있는 VOD는 건드리지 않음 | 변경 0건 |
| P2-07 | director 전체 처리 후 채움률 | ≥ 90% (기존 NULL 중) |
| P2-08 | cast_lead 전체 처리 후 채움률 | ≥ 85% |
| P2-09 | rating 전체 처리 후 채움률 | ≥ 95% |
| P2-10 | release_date 전체 처리 후 채움률 | ≥ 90% |
| P2-11 | rag_confidence 평균 | ≥ 0.80 |
| P2-12 | 처리 시간 director 15K건 | ≤ 50시간 (배치 병렬) |
| P2-13 | 오류율 (예외 발생 건) | ≤ 5% |

---

## 6. 병렬 처리 전략

```python
from concurrent.futures import ThreadPoolExecutor

# API 검색: 병렬 (IO bound)
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [executor.submit(self._search_and_validate, vod, column) for vod in batch]

# LLM 추론: 순차 (GPU bound, 단일 GPU)
# Ollama는 단일 스레드 처리 → LLM 호출은 직렬화
```

---

## 7. 주의사항

1. **기존 값 보호**: `WHERE director IS NULL` 조건으로 기존 데이터 덮어쓰기 방지
2. **IMDB Rate Limit**: requests 간 0.5초 sleep, API 쿼터 초과 시 자동 대기
3. **LLM 온도**: `temperature=0.2` (낮게) → 일관된 구조화 출력
4. **신뢰도 임계값**: `confidence < 0.6` → DB UPDATE 안 하고 수동 검증 큐 추가
5. **롤백 가능**: 처리 전 `rag_processed=FALSE` 기준으로 원상 복구 가능

---

**이전 단계**: PLAN_01_SETUP_PILOT.md
**다음 단계**: PLAN_03_QUALITY_MONITORING.md
