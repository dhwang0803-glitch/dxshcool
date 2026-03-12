# VOD_Embedding 세션 보고서 — 2026-03-12 오전

## 세션 요약

| 항목 | 내용 |
|------|------|
| 날짜 | 2026-03-12 07:09 ~ 07:35 |
| 작업 | 자동 루프 모니터링, CF_Engine 계획서 작성 |

---

## 파이프라인 현황 (2026-03-12 07:35 기준)

### STEP 1. 트레일러 크롤링
| 항목 | 값 |
|------|-----|
| 처리완료 | 5,240 / 11,508건 (45.5%) |
| 성공 | 5,134건 (98.0%) |
| 실패 | 106건 |
| 디스크 대기 | 109.6 MB (34개 파일) |

### STEP 2. CLIP 임베딩
| 항목 | 값 |
|------|-----|
| 처리완료 | 9,350건 |
| 성공 | 4,683건 |
| 실패 | 4,667건 (49.9%) — YouTube ID 중복 매핑 이슈 |
| 저장 배치 | 303개 (pkl) |

### STEP 3. Parquet
미생성 — 크롤링 완료 후 자동 생성 예정

---

## 이슈: 임베딩 실패율 ~50%

- **원인**: 여러 VOD가 동일한 YouTube ID(예: `vXtRnQofIWs`)에 매핑
- **처리**: 실패 건은 `embed_status.json`에 기록됨, 향후 재처리 가능
- **파이프라인 영향 없음** — 자동 루프 정상 진행 중

---

## 자동 루프 상태

- **루프 ID**: `b6tqfv3w7`
- **실행 횟수**: ~390회 이상
- **동작**: 60초 간격 대기 파일 감지 → 임베딩 → 보고서 저장 반복
- **종료 조건**: 크롤링 완료 + 대기 파일 0 → Parquet 자동 생성

---

## 내일 재개 시 확인 사항

```bash
cd C:/Users/user/Documents/GitHub/dxshcool/VOD_Embedding

# 1. 루프 생존 여부 확인
tail -3 data/auto_progress.log

# 2. 전체 현황
"C:/Users/user/miniconda3/envs/myenv/python.exe" scripts/progress_report.py

# 3. 루프 종료된 경우 재시작
#    (crawl_trailers.py + 임베딩 루프 재실행)
```

---

## 병행 작업: CF_Engine

- `CF_Engine/plans/implementation_plan.md` 작성 완료
- ALS 기반 협업 필터링 엔진 8단계 구현 계획 정의
- 다음 세션에서 구현 시작 예정 (`config/als_config.yaml` → `src/data_loader.py` 순)
