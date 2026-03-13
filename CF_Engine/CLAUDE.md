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
    → cf_recommendations 테이블 저장
    → API_Server /recommend/{user_id} 서빙
```

## 인터페이스

- **업스트림**: `Database_Design` — watch_history 테이블 (user_id_fk, vod_id_fk, completion_rate)
- **다운스트림**: `API_Server` — `/recommend/{user_id}` 엔드포인트가 이 결과를 반환
