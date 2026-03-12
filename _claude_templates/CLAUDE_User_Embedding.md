# User_Embedding — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

시청 이력(watch_history)과 VOD 결합 임베딩을 기반으로 **사용자 임베딩 벡터**를 학습하고 저장한다.

VOD 영상 임베딩(512차원) + VOD 메타데이터 임베딩(384차원)을 결합한 **896차원 VOD 벡터**와
동일한 잠재 공간에서 사용자 취향을 **896차원 벡터**로 표현한다.

## 벡터 차원 설계

| 임베딩 | 모델 | 차원 | 저장 위치 |
|--------|------|------|-----------|
| VOD 영상 임베딩 | CLIP ViT-B/32 | 512 | `vod_embedding` 테이블 |
| VOD 메타데이터 임베딩 | paraphrase-multilingual-MiniLM-L12-v2 | 384 | `vod_meta_embedding` 테이블 |
| **VOD 결합 임베딩** | L2 정규화 후 concat | **896** | 학습 파이프라인 내 결합 |
| **User 임베딩** | 행렬 분해 (ALS) | **896** | `user_embedding` 테이블 |

> ⚠️ **차원 축소 미확정**: 896차원 연산 부담 시 PCA/Autoencoder로 축소 예정.
> 원본 VOD 임베딩(512, 384)은 별도 테이블에 보존되므로 재학습 시 차원 변경 가능.

## 파일 위치 규칙 (MANDATORY)

```
User_Embedding/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 모델 하이퍼파라미터 yaml
└── docs/      ← 실험 리포트, 성능 평가 결과
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 행렬 분해 모델 (ALS) | `src/mf_model.py` |
| VOD 결합 임베딩 로더 | `src/vod_embedding_loader.py` |
| 학습 데이터 구성 (watch_history → 희소 행렬) | `src/data_loader.py` |
| 모델 학습 실행 | `scripts/train.py` |
| User 임베딩 DB 적재 | `scripts/export_to_db.py` |
| pytest | `tests/` |
| 하이퍼파라미터 설정 | `config/mf_config.yaml` |

**`User_Embedding/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import implicit                            # ALS (Alternating Least Squares)
import scipy.sparse                        # User-Item 희소 행렬
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
```

## 학습 파이프라인

```
[1] VOD 결합 임베딩 구성
    vod_embedding(512) + vod_meta_embedding(384)
    → 각각 L2 정규화 → concat → VOD 결합 벡터 [896차원]

[2] User-Item 행렬 구성
    watch_history → (user_id, vod_id, completion_rate) 희소 행렬

[3] ALS 학습
    item latent factor 초기값 = VOD 결합 벡터 [896차원]
    → user latent factor 학습 [896차원]

[4] DB 적재
    → user_embedding 테이블 (VECTOR(896))
```

## 하이퍼파라미터 (mf_config.yaml 초기값)

```yaml
factors: 896          # VOD 결합 임베딩 차원과 일치
iterations: 20
regularization: 0.01
alpha: 40             # implicit feedback 가중치
```

## 인터페이스

- **업스트림**: `VOD_Embedding` — `vod_embedding`(512차원), `vod_meta_embedding`(384차원)
- **업스트림**: `Database_Design` — `watch_history`, `user_embedding` 테이블 스키마
- **다운스트림**: `CF_Engine` — User 잠재 벡터를 협업 필터링 초기값으로 활용
- **다운스트림**: `Vector_Search` — User 임베딩으로 개인화 벡터 검색 (`/recommend/{user_id}`)
