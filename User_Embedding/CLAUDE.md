# User_Embedding — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

시청 이력(watch_history)을 기반으로 **사용자 임베딩 벡터**를 생성하고 `user_embedding` 테이블에 저장한다.

**이 브랜치의 범위**: 유저 정보만 벡터로 표현. VOD 벡터와의 행렬 분해(ALS)는 `CF_Engine` 브랜치에서 처리.

### 생성 방식
유저가 시청한 VOD의 결합 임베딩(896차원)을 `completion_rate`로 가중 평균하여 유저 벡터 생성.

```
watch_history (user_id, asset_id, completion_rate)
    ↓
각 VOD의 결합 임베딩(896차원) 조회
    ↓
weighted_mean(VOD_vectors, weights=completion_rates)
    ↓
L2 정규화 → user_embedding [896차원]
    ↓
user_embedding 테이블 upsert
```

---

## 벡터 차원 설계

| 임베딩 | 출처 | 차원 | 저장 위치 |
|--------|------|------|-----------|
| VOD 영상 임베딩 | CLIP ViT-B/32 (`VOD_Embedding` 브랜치) | 512 | `vod_embedding` (embedding_type='CLIP') |
| VOD 메타데이터 임베딩 | paraphrase-multilingual-MiniLM-L12-v2 (`VOD_Embedding` 브랜치) | 384 | `vod_embedding` (embedding_type='METADATA') |
| VOD 결합 임베딩 | L2 정규화 후 concat — 파이프라인 내 계산 | **896** | 저장 안 함 (런타임 계산) |
| **User 임베딩** | 시청 VOD 결합벡터 가중 평균 | **896** | `user_embedding` 테이블 |

> ⚠️ **차원 축소 미확정**: 896차원 연산 부담 시 PCA/Autoencoder로 축소 예정.
> 원본 VOD 임베딩(512, 384)은 별도 테이블에 보존되므로 재학습 시 차원 변경 가능.

---

## 파일 위치 규칙 (MANDATORY)

```
User_Embedding/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 설정 yaml
└── docs/
    ├── plans/    ← PLAN_00~03 설계 문서
    └── reports/  ← 실험 결과 리포트
```

| 파일 종류 | 저장 위치 | 상태 |
|-----------|-----------|------|
| VOD 결합 임베딩 로더 | `src/vod_embedding_loader.py` | 🔲 예정 |
| 유저 임베딩 생성 | `src/user_embedder.py` | 🔲 예정 |
| watch_history 데이터 로더 | `src/data_loader.py` | 🔲 예정 |
| DB 연결 헬퍼 | `src/db.py` | 🔲 예정 |
| 임베딩 생성 + 적재 실행 | `scripts/run_embed.py` | 🔲 예정 |
| pytest | `tests/` | 🔲 예정 |
| 파이프라인 설정 | `config/embed_config.yaml` | 🔲 예정 |

**`User_Embedding/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

---

## 기술 스택

```python
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
```

---

## 임베딩 스펙

- **저장 테이블**: `user_embedding`
- **차원**: `VECTOR(896)`
- **멱등성**: `ON CONFLICT (user_id) DO UPDATE SET embedding = EXCLUDED.embedding, updated_at = NOW()`
- **최소 시청 조건**: 시청 VOD가 1건 이상 + 결합 임베딩이 DB에 존재하는 경우만 생성

---

## 인터페이스

- **업스트림**: `VOD_Embedding` — `vod_embedding` 테이블 (CLIP 512 + METADATA 384 적재 완료 필요)
- **업스트림**: `Database_Design` — `watch_history`, `user_embedding` 테이블 스키마
- **다운스트림**: `CF_Engine` — User 벡터를 ALS 행렬 분해 초기값으로 활용
- **다운스트림**: `Vector_Search` — User 임베딩으로 개인화 벡터 검색 (`/recommend/{user_id}`)
