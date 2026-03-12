# CF_Engine 구현 계획

## 목표

`watch_history` 테이블 기반 ALS 협업 필터링 추천 엔진 구현.
유저별 Top-K VOD 추천 결과를 `cf_recommendations` 테이블에 저장하고 API_Server가 서빙.

---

## 기술 스택

```python
import implicit           # ALS (Alternating Least Squares)
import scipy.sparse       # User-Item 희소 행렬
import numpy as np
import psycopg2           # watch_history 로드, 추천 결과 저장
from dotenv import load_dotenv
```

---

## 파이프라인 흐름

```
watch_history 테이블 로드
    → User-Item 희소 행렬 구성 (scipy.sparse.csr_matrix)
    → ALS 학습 (factors=128, iterations=20, regularization=0.01)
    → 유저별 Top-K 추천 생성
    → cf_recommendations 테이블 저장
    → API_Server /recommend/{user_id} 서빙
```

---

## 구현 단계

### STEP 1. 데이터 로더 (`src/data_loader.py`)

**역할**: DB에서 `watch_history`를 읽어 ALS 입력용 희소 행렬로 변환

- DB 연결: `psycopg2` + `.env` (DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME)
- 쿼리: `SELECT user_id_fk, vod_id_fk, completion_rate FROM watch_history`
- `user_id_fk`, `vod_id_fk` → 정수 인덱스 매핑 (인코더 딕셔너리 반환)
- `completion_rate` → 신뢰도(confidence) 가중치로 사용
- 출력: `(csr_matrix, user_encoder, item_encoder)`

**핵심 설계**
```python
# completion_rate → confidence 변환 (implicit 라이브러리 관례)
confidence = 1 + alpha * completion_rate   # alpha=40 기본값
matrix = csr_matrix((confidence, (user_idx, item_idx)), shape=(n_users, n_items))
```

---

### STEP 2. ALS 모델 (`src/als_model.py`)

**역할**: `implicit` 라이브러리로 ALS 학습 및 추천 생성

- 모델: `implicit.als.AlternatingLeastSquares`
- 하이퍼파라미터: `config/als_config.yaml` 에서 로드
- 학습: `model.fit(item_user_matrix)`  ← implicit은 item×user 행렬 입력
- 추천: `model.recommend(user_id, user_items, N=K)`
- 모델 저장/로드: `numpy` npz 또는 `implicit` 내장 저장

**하이퍼파라미터 (기본값)**
| 파라미터 | 값 |
|----------|-----|
| factors | 128 |
| iterations | 20 |
| regularization | 0.01 |
| alpha | 40 |
| top_k | 20 |

---

### STEP 3. 추천 결과 포매터 (`src/recommender.py`)

**역할**: ALS 출력(인덱스 배열)을 원본 `vod_id_fk`로 역변환 후 DB 저장 형식 정리

- 인덱스 → `vod_id_fk` 역매핑
- 출력 형식: `List[dict(user_id_fk, vod_id_fk, score, rank)]`
- `cf_recommendations` 테이블 upsert 준비

---

### STEP 4. 학습 스크립트 (`scripts/train.py`)

**역할**: 전체 파이프라인 실행 진입점

```
실행: python scripts/train.py --config config/als_config.yaml
```

1. `.env` 로드 → DB 연결
2. `data_loader` → 희소 행렬 생성
3. `als_model` → 학습
4. `recommender` → 추천 결과 생성
5. `export_to_db` → DB 저장
6. 학습 완료 로그 출력 (소요시간, 유저 수, 아이템 수)

---

### STEP 5. 평가 스크립트 (`scripts/evaluate.py`)

**역할**: 추천 품질 측정

- Hold-out 방식: 유저별 최근 시청 1건을 테스트셋으로 분리
- 지표:
  - **NDCG@K** (Normalized Discounted Cumulative Gain)
  - **MRR** (Mean Reciprocal Rank)
  - **Hit Rate@K**
- 결과를 `docs/eval_report_{날짜}.md` 로 저장

```
실행: python scripts/evaluate.py --config config/als_config.yaml --k 20
```

---

### STEP 6. DB 적재 스크립트 (`scripts/export_to_db.py`)

**역할**: 추천 결과를 `cf_recommendations` 테이블에 upsert

- `psycopg2` executemany / COPY 방식으로 대량 적재
- `ON CONFLICT (user_id_fk, vod_id_fk) DO UPDATE SET score=..., updated_at=NOW()`
- 배치 크기: 1,000건 단위

---

### STEP 7. 설정 파일 (`config/als_config.yaml`)

```yaml
model:
  factors: 128
  iterations: 20
  regularization: 0.01
  alpha: 40

recommend:
  top_k: 20

db:
  batch_size: 1000
```

---

### STEP 8. 테스트 (`tests/`)

| 파일 | 대상 |
|------|------|
| `tests/test_data_loader.py` | 희소 행렬 shape, 인코더 정합성 |
| `tests/test_als_model.py` | 학습 후 벡터 shape, 추천 결과 K개 |
| `tests/test_recommender.py` | 역매핑 정확성, 출력 형식 |

---

## 구현 순서 (권장)

```
1. config/als_config.yaml
2. src/data_loader.py
3. src/als_model.py
4. src/recommender.py
5. scripts/train.py
6. scripts/export_to_db.py
7. tests/
8. scripts/evaluate.py
```

---

## 인터페이스

| 방향 | 브랜치 | 테이블 | 컬럼 |
|------|--------|--------|------|
| 업스트림 | `Database_Design` | `watch_history` | user_id_fk, vod_id_fk, completion_rate |
| 다운스트림 | `API_Server` | `cf_recommendations` | user_id_fk, vod_id_fk, score, rank |
