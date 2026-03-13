# CF_Engine — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

시청 이력(watch_history) 기반 **협업 필터링(Collaborative Filtering)** 추천 엔진.
ALS(Alternating Least Squares) 행렬 분해로 User-Item 잠재 벡터를 학습하고,
추천 결과를 DB에 저장하여 API_Server가 실시간으로 서빙할 수 있게 한다.

## 파일 위치 규칙 (MANDATORY)

```
CF_Engine/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 모델 하이퍼파라미터 yaml
└── docs/      ← 실험 리포트, 성능 평가 결과
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 행렬 분해 알고리즘 구현 | `src/als_model.py` |
| 데이터 로더 (watch_history → 희소 행렬) | `src/data_loader.py` |
| 추천 결과 포매터 | `src/recommender.py` |
| 모델 학습 실행 | `scripts/train.py` |
| 모델 평가 (NDCG, MRR) | `scripts/evaluate.py` |
| 추천 결과 DB 적재 | `scripts/export_to_db.py` |
| pytest | `tests/` |
| 하이퍼파라미터 설정 | `config/als_config.yaml` |

**`CF_Engine/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import implicit           # ALS (Alternating Least Squares)
import scipy.sparse       # User-Item 희소 행렬
import numpy as np
import psycopg2           # watch_history 로드, 추천 결과 저장
from dotenv import load_dotenv
```

## 학습 파이프라인

```
watch_history 테이블 로드
    → User-Item 희소 행렬 구성
    → ALS 학습 (factors=128, iterations=20, regularization=0.01)
    → 유저별 Top-K 추천 생성
    → [권한에 따라 분기] ─┬─ DB 쓰기 권한 있음 (조장) → serving.vod_recommendation upsert
                          └─ DB 쓰기 권한 없음 (팀원) → data/cf_recommendations_YYYYMMDD.parquet 저장
    → API_Server /recommend/{user_id} 서빙
```

## ⚠️ DB 쓰기 권한 분리 (MANDATORY)

### 배경
- **팀원**: DB 읽기 권한만 보유 — `watch_history` 로드는 가능, `serving.vod_recommendation` 직접 INSERT 불가
- **조장 (dhwang0803)**: DB 쓰기 권한 보유 — parquet 파일을 받아 DB에 최종 적재

### `scripts/train.py` 실행 방법

```bash
# 팀원 (DB 쓰기 권한 없음) — parquet 출력
python scripts/train.py --output parquet
# → data/cf_recommendations_YYYYMMDD.parquet 생성 후 조장에게 전달

# 조장 — parquet 받아서 DB 직접 적재
python scripts/train.py --from-parquet data/cf_recommendations_YYYYMMDD.parquet
# → serving.vod_recommendation DELETE + INSERT

# 조장 — DB 직접 학습 + 적재 (1회성 전체 실행)
python scripts/train.py
```

### Parquet 스키마

```python
# data/cf_recommendations_YYYYMMDD.parquet
# 컬럼: user_id_fk, vod_id_fk, rank, score, recommendation_type
# 타입: str,        str,        int,  float, str
```

### 구현 요구사항 (scripts/train.py 수정 필요)

| 옵션 | 동작 |
|------|------|
| `(없음)` | DB 학습 + serving.vod_recommendation 직접 적재 (조장 전용) |
| `--output parquet` | DB 읽기 + 추천 생성 + parquet 저장 (팀원용) |
| `--from-parquet <파일>` | parquet → serving.vod_recommendation 적재 (조장 전용) |
| `--dry-run` | DB 저장/parquet 저장 없이 추천 결과만 로그 출력 |

> `--output parquet` 모드는 DB 쓰기를 시도하지 않으므로 팀원 환경에서 안전하게 실행 가능.
> `--from-parquet` 모드는 `export_to_db.py`의 `export()` 함수를 재사용.

### recommendation_type 확정값

- **사용값**: `'COLLABORATIVE'` (config/als_config.yaml 반영 완료)
- **DB CHECK 허용값**: `'VISUAL_SIMILARITY'` | `'COLLABORATIVE'` | `'HYBRID'`
  (Database_Design/schemas/create_embedding_tables.sql `chk_rec_type` 참조)

### serving.vod_recommendation UNIQUE constraint

- **확인 완료**: `UNIQUE (user_id_fk, vod_id_fk)`
- recommendation_type 미포함 → 타입별 공존 불가
- **DELETE+INSERT 패턴 유지** (UPSERT 전환 불필요)

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.watch_history` | `user_id_fk` | VARCHAR | 유저 식별자 |
| `public.watch_history` | `vod_id_fk` | VARCHAR | VOD 식별자 |
| `public.watch_history` | `completion_rate` | FLOAT | confidence 계산 (alpha=40) |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `serving.vod_recommendation` | `user_id_fk` | VARCHAR | UNIQUE(user_id_fk, vod_id_fk) |
| `serving.vod_recommendation` | `vod_id_fk` | VARCHAR | UNIQUE(user_id_fk, vod_id_fk) |
| `serving.vod_recommendation` | `rank` | SMALLINT | Top-K 순위 |
| `serving.vod_recommendation` | `score` | REAL | ALS 추천 점수 |
| `serving.vod_recommendation` | `recommendation_type` | VARCHAR | 고정값: `'COLLABORATIVE'` |
