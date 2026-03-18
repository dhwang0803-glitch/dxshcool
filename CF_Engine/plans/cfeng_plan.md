# CF_Engine 구현 계획

## 목표

`watch_history` 테이블 기반 ALS 협업 필터링 추천 엔진 구현.
유저별 Top-K VOD 추천 결과를 `serving.vod_recommendation` 테이블에 저장하고 API_Server가 서빙.

---

## 기술 스택

```python
import implicit           # ALS (Alternating Least Squares) 0.7.x
import scipy.sparse       # User-Item 희소 행렬
import numpy as np
import psycopg2           # watch_history 로드, 추천 결과 저장
from dotenv import load_dotenv
import yaml               # 하이퍼파라미터 설정
```

---

## 파이프라인 흐름

```
watch_history 테이블 로드
    → User-Item 희소 행렬 구성 (scipy.sparse.csr_matrix)
    → ALS 학습 (factors=128, iterations=20, regularization=0.01)
    → 유저별 Top-K 추천 생성
    → [권한에 따라 분기] ─┬─ DB 쓰기 권한 있음 (조장) → serving.vod_recommendation DELETE+INSERT
                          └─ DB 쓰기 권한 없음 (팀원) → data/cf_recommendations_YYYYMMDD.parquet 저장
    → API_Server /recommend/{user_id} 서빙
```

---

## 구현 현황 (2026-03-18 기준)

| 파일 | 상태 | 설명 |
|------|------|------|
| `config/als_config.yaml` | ✅ 완료 | 하이퍼파라미터, recommendation_type |
| `src/data_loader.py` | ✅ 완료 | DB → csr_matrix 변환, filter_quality 옵션 포함 |
| `src/als_model.py` | ✅ 완료 | ALS 학습 + 전체 유저 추천 생성 |
| `src/recommender.py` | ✅ 완료 | 인덱스 → vod_id_fk 역변환, 레코드 포매팅 |
| `scripts/train.py` | ✅ 완료 | --output parquet / --from-parquet / --dry-run 옵션 구현 |
| `scripts/export_to_db.py` | ✅ 완료 | serving.vod_recommendation DELETE+INSERT |
| `scripts/evaluate.py` | ✅ 완료 | NDCG@K, MRR, HitRate@K, --filter-quality 옵션 포함 |
| `scripts/score_cutoff_analysis.py` | ✅ 완료 | 유저별 점수 급락 지점 분석 |
| `scripts/cold_impact_analysis.py` | ✅ 완료 | cold VOD 비중 영향 분석 |
| `scripts/cutoff1_sample_report.py` | ✅ 완료 | 1위 급락 유저 샘플 리포트 생성 |
| `scripts/full_eval.py` | ✅ 완료 | 필터 전/후 비교 + 세그먼트 분석 |
| `scripts/inspect_recommendations.py` | ✅ 완료 | 추천 결과 육안 검증 (md 저장 기능 포함) |
| `scripts/pilot_test.py` | ✅ 완료 | 파일럿 테스트 |
| `scripts/pilot_cutoff_visual.py` | ✅ 완료 | 파일럿 급락 지점 시각화 |
| `tests/` | ✅ 9/9 PASSED | data_loader, als_model, recommender |

---

## 확정 하이퍼파라미터

| 파라미터 | 값 |
|----------|-----|
| factors | 128 |
| iterations | 20 |
| regularization | 0.01 |
| alpha | 40 |
| top_k | 10 |
| recommendation_type | `"COLLABORATIVE"` |
| batch_size | 1,000 |

---

## 공식 평가 결과 (2026-03-17 확정, k=10)

| 지표 | 필터 없음 | 필터 ON | 변화 |
|------|----------|---------|------|
| NDCG@10 | 0.2353 | 0.2659 | +13.0% |
| MRR | 0.1900 | 0.2193 | +15.4% |
| HitRate@10 | 0.3829 | 0.4176 | +9.1% |
| Precision@10 | 0.0383 | 0.0418 | +9.1% |
| Coverage | 0.0670 | 0.0825 | +23.1% |

### 세그먼트별 성능 (필터 ON 기준)

| 세그먼트 | 유저 수 | NDCG@10 | HitRate@10 |
|----------|---------|---------|------------|
| Cold (2~4개) | 74,338명 | 0.3593 | 0.5182 |
| Warm (5~19개) | 52,717명 | 0.2068 | 0.3771 |
| Hot (20개+) | 20,049명 | 0.0744 | 0.1510 |

---

## DB / 유저 현황 (2026-03-18 기준)

| 항목 | 수치 |
|------|------|
| 전체 VOD | 166,159건 |
| 추천 가능 VOD (poster+embedding 둘 다) | 119,730건 (72.1%) |
| cold VOD (둘 중 하나 없음) | 46,429건 (27.9%) |
| 전체 유저 | 242,702명 |
| 5개 미만 시청 유저 | 130,883명 (53.9%) |
| cold VOD 시청 유저 | 90,593명 (37.3%) |
| cold 비중 50% 초과 유저 | 33,891명 (14.0%) |
| 시청이력 중 cold 비율 | 21.1% |

---

## 다음 작업 (2026-03-18 기준)

| # | 작업 | 상태 |
|---|------|------|
| Step 3 | score_cutoff_analysis --users 5000 재실행 (전체 기준 k 지점 확정) | ✅ 완료 (2026-03-18) |
| Step 5 | 배우/감독 기반 추천 (`src/content_recommender.py`) | ✅ 완료 (2026-03-18) |
| Step 6 | 추천 결과 적절성·정확도 평가 스크립트 작성 + 리포트 | 🔲 예정 |

### Step 3 결과 — 5000명 샘플 (2026-03-18 확정, 품질 필터 ON)

| 지표 | 값 |
|------|----|
| 50% 유저 급락 기준 | K=1 이내 |
| 75% 유저 급락 기준 | K=2 이내 |
| 90% 유저 급락 기준 | K=4 이내 |
| 급락 지점 평균 점수 | 0.8622 |
| Top-20 끝 평균 점수 | 0.5011 |
| 권장 K (75% 커버) | 2 |

> 64.1% 유저가 1위에서 급락 → K=2 이내로 의미있는 추천 완료됨.
> **폴백 전략 확정**: 1~2위 고품질 필터 ON + 3~10위 저품질 인기 VOD 폴백
> 리포트: `docs/score_cutoff_report_20260318_151010.md`

### Step 6 — 추천 결과 적절성·정확도 평가 (예정)

#### 목적

ALS + content_boost 파이프라인이 실제 데이터 기준으로 **얼마나 적절하고 정확한 추천**을 하는지 정량·정성 평가.

#### 평가 항목

| 구분 | 항목 | 방법 |
|------|------|------|
| **정확도** | NDCG@K, MRR, HitRate@K | `evaluate.py` 기존 지표 활용 |
| **content_boost 적절성** | boost된 VOD가 실제로 해당 감독/배우 작품인지 | 샘플 유저 추출 후 검증 |
| **content_boost 전/후 비교** | boost 적용 전/후 지표 변화 | ALS 단독 vs ALS+boost 비교 |
| **다양성** | Coverage 변화 | boost 전/후 Coverage 비교 |
| **정성 평가** | 샘플 유저 추천 목록 육안 검증 | 시청 이력 vs 추천 결과 비교 |

#### 구현 파일 (예정)

| 파일 | 내용 |
|------|------|
| `scripts/eval_content_boost.py` | content_boost 전/후 지표 비교 + 적절성 검증 |
| `docs/eval_content_boost_report.md` | 평가 결과 리포트 |

#### 실행 방법 (예정)

```bash
python scripts/eval_content_boost.py --users 1000 --filter-quality
```

---

### Step 5 — 배우/감독 기반 추천 후처리 상세 (확정)

- ALS Top-K 결과에 **후처리로 1~2개 추가**하는 방식
- `recommendation_type`: **COLLABORATIVE 유지** (DB 스키마 변경 없음)
- 트리거 조건: 동일 감독 3편 이상 OR 동일 배우 3편 이상 시청한 유저에게만 적용
- 추가 개수: 감독 조건 충족 시 1개 + 배우 조건 충족 시 1개 (최대 2개)
- 추가 위치: ALS rank 뒤에 rank+1, rank+2로 붙임
- 후보 조건: 미시청 + 품질 필터(poster+embedding) 통과 VOD
- cast 컬럼 형태: JSON 배열 `["현빈", ...]` or 쉼표 구분 `"정형돈, 데프콘"` 혼재 → 파싱 처리
- 구현 파일: `src/content_recommender.py` + `scripts/train.py` 후처리 연동

---

## 실행 방법

```bash
# 팀원 (DB 쓰기 권한 없음)
python scripts/train.py --output parquet

# 조장 — parquet 받아서 DB 적재
python scripts/train.py --from-parquet data/cf_recommendations_YYYYMMDD.parquet

# 조장 — DB 직접 학습 + 적재
python scripts/train.py

# dry-run
python scripts/train.py --dry-run

# 성능 평가
python scripts/evaluate.py --filter-quality --k 10

# cold 비중 분석
python scripts/cold_impact_analysis.py

# 급락 지점 분석 (5,000명 샘플)
python scripts/score_cutoff_analysis.py --users 5000 --filter-quality
```

---

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.watch_history` | `user_id_fk` | VARCHAR | 유저 식별자 |
| `public.watch_history` | `vod_id_fk` | VARCHAR | VOD 식별자 |
| `public.watch_history` | `completion_rate` | FLOAT | confidence 계산 (alpha=40) |
| `public.vod` | `poster_url` | VARCHAR | 품질 필터 기준 |
| `public.vod` | `director` | VARCHAR(255) | 배우/감독 추천용 |
| `public.vod` | `cast_lead` | TEXT | 배우/감독 추천용 |
| `public.vod` | `cast_guest` | TEXT | 배우/감독 추천용 |
| `public.vod_embedding` | `vod_id_fk` | VARCHAR | 품질 필터 기준 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `serving.vod_recommendation` | `user_id_fk` | VARCHAR | UNIQUE(user_id_fk, vod_id_fk) |
| `serving.vod_recommendation` | `vod_id_fk` | VARCHAR | UNIQUE(user_id_fk, vod_id_fk) |
| `serving.vod_recommendation` | `rank` | SMALLINT | Top-K 순위 |
| `serving.vod_recommendation` | `score` | REAL | ALS 추천 점수 |
| `serving.vod_recommendation` | `recommendation_type` | VARCHAR | 고정값: `'COLLABORATIVE'` |
