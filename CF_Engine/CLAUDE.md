# CF_Engine — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

시청 이력(watch_history) 기반 **협업 필터링(Collaborative Filtering)** 추천 엔진.
ALS(Alternating Least Squares) 행렬 분해로 User-Item 잠재 벡터를 학습하고,
추천 후보(top 20)를 `serving.vod_recommendation`에 저장한다.
이후 **Hybrid_Layer**가 Vector_Search 후보와 합쳐 리랭킹 → `serving.hybrid_recommendation` → API_Server 서빙.

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
    → 유저별 Top-20 추천 생성
    → [권한에 따라 분기] ─┬─ DB 쓰기 권한 있음 (조장) → serving.vod_recommendation DELETE+INSERT
                          └─ DB 쓰기 권한 없음 (팀원) → data/cf_recommendations_YYYYMMDD.parquet 저장
    → Hybrid_Layer가 소비 → 리랭킹 → serving.hybrid_recommendation → API_Server 서빙
```

## 실행 방법

```bash
# DB 학습 + 적재
python scripts/train.py

# DB 저장 없이 추천 결과만 확인
python scripts/train.py --dry-run
```

### recommendation_type 확정값

- **사용값**: `'COLLABORATIVE'` (config/als_config.yaml 반영 완료)
- **DB CHECK 허용값**: `'VISUAL_SIMILARITY'` | `'COLLABORATIVE'` | `'HYBRID'`
  (Database_Design/schemas/create_embedding_tables.sql `chk_rec_type` 참조)

### serving.vod_recommendation UNIQUE constraint

- **변경 완료 (2026-03-20)**: `UNIQUE (user_id_fk, vod_id_fk, recommendation_type)`
- recommendation_type 포함 → CF/Vector/Hybrid 타입별 독립 저장 가능
- Cloud Run Jobs 독립 실행 시 동일 user-vod 쌍 충돌 방지
- UPSERT(`ON CONFLICT ... DO UPDATE`) 전환 가능 (현재 DELETE+INSERT도 정상 동작)

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
| `serving.vod_recommendation` | `user_id_fk` | VARCHAR | UNIQUE(user_id_fk, vod_id_fk, recommendation_type) |
| `serving.vod_recommendation` | `vod_id_fk` | VARCHAR | UNIQUE(user_id_fk, vod_id_fk, recommendation_type) |
| `serving.vod_recommendation` | `rank` | SMALLINT | Top-K 순위 |
| `serving.vod_recommendation` | `score` | REAL | ALS 추천 점수 |
| `serving.vod_recommendation` | `recommendation_type` | VARCHAR | 고정값: `'COLLABORATIVE'` |
