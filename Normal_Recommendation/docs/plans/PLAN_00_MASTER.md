# PLAN_00: Normal Recommendation 파이프라인 마스터 플랜

**브랜치**: Normal_Recommendation
**담당**: 담당자 C (Cold Start 대응)
**작성일**: 2026-03-17
**목표**: 시청 이력 없는 신규 유저(Cold Start) 대상으로 장르/콘텐츠유형별 인기 VOD Top-N을 생성하여 `serving.vod_recommendation` 테이블에 적재

---

## 전체 구조

```
[PLAN_01] vod 테이블 + watch_history 로드
             → 인기 지표 계산 (조회수 + 평점 가중합)
             → 장르/콘텐츠유형별 Top-N 추천 결과 생성
             → data/recommendations_popular_YYYYMMDD.parquet 저장
                             ↓
[PLAN_02] parquet → serving.vod_recommendation 적재
                   (조장 전용: DB 쓰기 권한 필요)
```

---

## 단계별 요약

| 단계 | 파일 | 입력 | 출력 | 예상 시간 |
|------|------|------|------|---------|
| PLAN_01 | `scripts/run_pipeline.py` | vod + watch_history 테이블 | `data/recommendations_popular_YYYYMMDD.parquet` | 수 분 |
| PLAN_02 | `scripts/export_to_db.py` | parquet 파일 | `serving.vod_recommendation` | 수 분 |

---

## 인기 지표 계산 방식

### 조회수 (watch_count)
`watch_history` 테이블에서 `vod_id_fk` 기준 시청 건수 집계.

```sql
SELECT vod_id_fk, COUNT(*) AS watch_count
FROM public.watch_history
GROUP BY vod_id_fk;
```

### 인기 점수 공식

```
score = w1 * norm(watch_count) + w2 * norm(rating)
```

| 파라미터 | 기본값 | 설명 |
|---------|-------|------|
| `w1` | 0.7 | 조회수 가중치 |
| `w2` | 0.3 | 평점 가중치 |
| `top_n` | 20 | 카테고리별 추천 개수 |

- **정규화**: min-max 정규화 (0~1 범위)
- **평점 NULL 처리**: 0으로 대체 후 정규화
- **장르 분리**: 슬래시(`/`) 구분 다중 장르 → 각 장르에 개별 등록

---

## ⚠️ DB 쓰기 권한 분리

### 배경
- **팀원**: DB 읽기 권한만 보유 → parquet 파일로 저장 후 조장에게 전달
- **조장 (dhwang0803)**: DB 쓰기 권한 보유 → parquet 받아서 DB 최종 적재

### `scripts/run_pipeline.py` 실행 방법

```bash
# 팀원 (DB 쓰기 권한 없음) — parquet 출력
python scripts/run_pipeline.py --output parquet
# → data/recommendations_popular_YYYYMMDD.parquet 생성 후 조장에게 전달

# 조장 — parquet 받아서 DB 직접 적재
python scripts/export_to_db.py --from-parquet data/recommendations_popular_YYYYMMDD.parquet

# 조장 — DB 직접 실행 + 적재 (1회성 전체)
python scripts/run_pipeline.py
```

### Parquet 스키마

```python
# data/recommendations_popular_YYYYMMDD.parquet
# 컬럼: vod_id_fk, rank, score, recommendation_type, genre, ct_cl
# 타입: str,       int,  float, str,                  str,   str
```

---

## 파일 구조

```
Normal_Recommendation/
├── src/
│   ├── popularity.py           ← PLAN_01: 인기 VOD 집계 로직 (import 전용)
│   └── db.py                   ← DB 연결 공통 모듈 (import 전용)
├── scripts/
│   ├── run_pipeline.py         ← PLAN_01: 추천 결과 생성 실행
│   └── export_to_db.py         ← PLAN_02: 추천 결과 DB 적재 (조장 전용)
├── tests/
│   └── test_popularity.py      ← pytest
├── config/
│   └── recommend_config.yaml   ← top_n, 가중치 설정값
└── docs/
    ├── plans/
    │   ├── PLAN_00_MASTER.md   ← 이 파일
    │   ├── PLAN_01_POPULARITY.md
    │   └── PLAN_02_EXPORT_DB.md
    └── reports/                ← 실험 리포트
```

---

## 핵심 제약 및 전제

| 항목 | 내용 |
|------|------|
| vod 테이블 | 166,159건 (`full_asset_id`, `genre`, `ct_cl`, `rating`) |
| watch_history 테이블 | 약 44,000,000건 (`vod_id_fk`, `user_id_fk`) |
| 추천 대상 유저 | Cold Start 유저 (시청 이력 없음) → user_id_fk=NULL |
| recommendation_type | `'POPULAR'` 고정값 |
| source_vod_id | NULL (콘텐츠 기반 아님) |
| UNIQUE constraint | `serving.vod_recommendation` UNIQUE (user_id_fk, vod_id_fk) |

---

## 진행 체크리스트

### PLAN_01: 인기 VOD 집계 및 추천 결과 생성
- [ ] `src/popularity.py` 구현 (인기 지표 계산 로직)
- [ ] `src/db.py` 구현 (DB 연결 공통 모듈)
- [ ] `config/recommend_config.yaml` 작성 (top_n, 가중치)
- [ ] `scripts/run_pipeline.py` 구현 (실행 스크립트)
- [ ] parquet 저장 확인

### PLAN_02: DB 적재
- [ ] `scripts/export_to_db.py` 구현
- [ ] 조장에게 parquet 전달
- [ ] `serving.vod_recommendation` 적재 완료 확인

### 테스트
- [ ] `tests/test_popularity.py` 작성 (pytest)
- [ ] 단위 테스트 전체 통과 확인

---

**다음**: PLAN_01_POPULARITY.md
