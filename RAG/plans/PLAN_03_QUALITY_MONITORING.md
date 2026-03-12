# Phase 3: 품질 평가 & 모니터링

**단계**: Phase 3 / 4
**목표**: RAG 처리 결과 품질 검증 + 이상 탐지 + 최종 통계 리포트 생성
**산출물**: `src/monitoring.py`, `src/quality_analysis.py`, `reports/phase3_report.md`
**선행 조건**: Phase 2 완료 (HIGH 우선순위 처리 완료)

---

## 1. monitoring.py

### RAGMonitor 클래스

| 메서드 | 역할 |
|--------|------|
| `log_search(vod_id, column, result, source, duration, confidence)` | 처리 로그 기록 (SQLite 또는 CSV) |
| `track_success_rate(column)` | 컬럼별 성공률 집계 |
| `detect_anomalies()` | 신뢰도 < 0.6 이상 탐지, 결과 길이 이상 탐지 |
| `generate_daily_report()` | 일일 처리 통계 |

### 로그 스키마

```python
LOG_SCHEMA = {
    'vod_id':     str,    # full_asset_id
    'column':     str,    # director / cast_lead / rating / release_date
    'result':     str,    # 추출된 값 (None이면 'NULL')
    'source':     str,    # IMDB / Wikipedia / KMRB
    'confidence': float,  # 0.0 ~ 1.0
    'duration_s': float,  # 처리 시간(초)
    'processed_at': str,  # ISO timestamp
    'is_anomaly': bool,   # 이상 탐지 여부
}
```

---

## 2. quality_analysis.py

### QualityAnalyzer 클래스

| 메서드 | 역할 |
|--------|------|
| `sample_validation(sample_size=200)` | 랜덤 샘플링 후 수동 검증 CSV 생성 |
| `confidence_distribution()` | 신뢰도 분포 분석 (히스토그램 데이터) |
| `identify_failures()` | NULL 잔존 / 신뢰도 낮은 항목 목록 |
| `compare_before_after()` | 처리 전후 결측률 비교 |
| `suggest_improvements()` | 성공률 낮은 패턴 분석 및 개선 제안 |

### 샘플 검증 CSV 형식

```csv
vod_id,asset_nm,column,rag_result,rag_source,rag_confidence,manual_check,correct
full_asset_id_001,기생충,director,봉준호,IMDB,0.95,,
full_asset_id_002,어벤져스,cast_lead,"로버트 다우니 주니어",IMDB,0.88,,
```

---

## 3. 최종 통계 리포트 형식

```markdown
## 결측치 처리 결과 요약

| 컬럼 | 처리 전 결측 | 처리 후 결측 | 채움률 | 평균 신뢰도 |
|------|------------|------------|--------|------------|
| director | 15,000 | 750 | 95.0% | 0.91 |
| cast_lead | 25,000 | 2,500 | 90.0% | 0.87 |
| rating | 5,000 | 100 | 98.0% | 0.97 |
| release_date | 8,000 | 400 | 95.0% | 0.93 |

## 처리 성능

| 항목 | 값 |
|------|---|
| 총 처리 건수 | 53,000건 |
| 총 처리 시간 | X시간 |
| 평균 처리 속도 | X건/시간 |
| 오류율 | X% |

## 이상 탐지

| 항목 | 건수 |
|------|------|
| 신뢰도 < 0.6 | X건 |
| 수동 검증 필요 | X건 |
```

---

## 4. 테스트 항목 (tests/test_phase3_quality.py)

| ID | 항목 | 기대값 |
|----|------|--------|
| P3-01 | RAGMonitor 초기화 | 예외 없음 |
| P3-02 | log_search 기록 후 조회 | 기록된 데이터 일치 |
| P3-03 | track_success_rate("director") | 0~1 범위 float |
| P3-04 | detect_anomalies() 실행 | 이상 목록 반환 (건수 ≥ 0) |
| P3-05 | sample_validation(200) CSV 생성 | 200행 CSV 파일 생성됨 |
| P3-06 | compare_before_after() | 채움률 증가 확인 |
| P3-07 | director 최종 채움률 | ≥ 90% |
| P3-08 | 전체 rag_confidence 평균 | ≥ 0.80 |
| P3-09 | 수동 검증 큐 항목 수 | ≤ 10% of 처리 건수 |
| P3-10 | phase3_report.md 생성 | 파일 존재, 비어있지 않음 |

---

## 5. 주의사항

1. **수동 검증 CSV**: `reports/manual_validation_sample.csv` 저장 후 팀원 검토
2. **이상 항목 처리**: 신뢰도 < 0.6 항목은 `reports/anomalies.csv`에 별도 기록
3. **롤백 쿼리 준비**: `UPDATE vod SET director=NULL, rag_processed=FALSE WHERE rag_confidence < 0.6`

---

**이전 단계**: PLAN_02_HIGH_PRIORITY.md
**다음 단계**: PLAN_04_MEDIUM_PRIORITY.md (선택)
