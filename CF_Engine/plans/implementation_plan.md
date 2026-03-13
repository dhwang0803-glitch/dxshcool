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
    → serving.vod_recommendation 테이블 저장
    → API_Server /recommend/{user_id} 서빙
```

---

## 구현 현황

| 파일 | 상태 | 설명 |
|------|------|------|
| `config/als_config.yaml` | ✅ 완료 | 하이퍼파라미터, recommendation_type |
| `src/data_loader.py` | ✅ 완료 | DB → csr_matrix 변환, 인코더 반환 |
| `src/als_model.py` | ✅ 완료 | ALS 학습 + 전체 유저 추천 생성 |
| `src/recommender.py` | ✅ 완료 | 인덱스 → vod_id_fk 역변환, 레코드 포매팅 |
| `scripts/train.py` | ✅ 완료 | 전체 파이프라인 실행 진입점 |
| `scripts/export_to_db.py` | ✅ 완료 | serving.vod_recommendation DELETE+INSERT |
| `scripts/evaluate.py` | ✅ 완료 | NDCG@K, MRR, HitRate@K 평가 |
| `tests/test_data_loader.py` | ✅ 완료 | 희소 행렬 shape, 인코더 정합성, confidence 값 |
| `tests/test_als_model.py` | ✅ 완료 | 학습 후 벡터 shape, 추천 결과 K개 |
| `tests/test_recommender.py` | ✅ 완료 | 역매핑 정확성, 출력 형식, recommendation_type |

**테스트 결과**: 9/9 PASSED

---

## 실행 방법

```bash
# 전체 파이프라인 (학습 + DB 저장)
python scripts/train.py

# dry-run (DB 저장 없이 추천만 생성)
python scripts/train.py --dry-run

# 성능 평가
python scripts/evaluate.py --k 20
```

---

## STEP별 상세 설계

### STEP 1. 데이터 로더 (`src/data_loader.py`)

- DB 연결: `psycopg2` + `.env` (os.getenv)
- 쿼리: `SELECT user_id_fk, vod_id_fk, completion_rate FROM watch_history WHERE completion_rate IS NOT NULL`
- `completion_rate` → confidence = `1 + alpha * completion_rate` (alpha=40)
- 출력: `(csr_matrix, user_encoder, item_encoder, user_decoder, item_decoder)`

### STEP 2. ALS 모델 (`src/als_model.py`)

- `implicit.als.AlternatingLeastSquares` (v0.7.x)
- `model.fit(mat)` — user×item 행렬 직접 입력 (v0.7 API, mat.T 불필요)
- `model.recommend(user_ids, mat[user_ids], N=top_k, filter_already_liked_items=True)`
- 배치 추천: 전체 유저 한 번에 처리

### STEP 3. 추천 결과 포매터 (`src/recommender.py`)

- 인덱스 → `vod_id_fk` 역매핑
- 출력: `List[dict(user_id_fk, vod_id_fk, score, rank, recommendation_type)]`

### STEP 4. 학습 스크립트 (`scripts/train.py`)

1. `.env` 로드 → DB 연결
2. `data_loader` → 희소 행렬
3. `als_model` → 학습
4. `als_model` → 추천 생성
5. `recommender` → 레코드 변환
6. `export_to_db` → DB 저장

### STEP 5. 평가 스크립트 (`scripts/evaluate.py`)

- Hold-out: 유저별 마지막 아이템 1건 테스트셋 분리
- 지표: NDCG@K, MRR, HitRate@K
- 결과: `docs/eval_report_{날짜}.md`

### STEP 6. DB 적재 (`scripts/export_to_db.py`)

- DELETE 기존 CF 추천 (해당 유저 + recommendation_type)
- INSERT 신규 추천 (배치 1,000건)
- unique constraint 미확인으로 DELETE+INSERT 패턴 사용

---

## 하이퍼파라미터 (`config/als_config.yaml`)

| 파라미터 | 값 |
|----------|-----|
| factors | 128 |
| iterations | 20 |
| regularization | 0.01 |
| alpha | 40 |
| top_k | 20 |
| recommendation_type | "CF" ← **조장 확인 후 변경** |
| batch_size | 1,000 |

---

## ⚠️ 미결 사항

- [ ] `recommendation_type` 허용값 조장 확인 후 `config/als_config.yaml` 업데이트
- [ ] `serving.vod_recommendation` unique constraint 확인 후 필요시 UPSERT로 전환

---

## 인터페이스

| 방향 | 브랜치 | 테이블 | 컬럼 |
|------|--------|--------|------|
| 업스트림 | `Database_Design` | `watch_history` | user_id_fk, vod_id_fk, completion_rate |
| 다운스트림 | `API_Server` | `serving.vod_recommendation` | user_id_fk, vod_id_fk, score, rank, recommendation_type |
