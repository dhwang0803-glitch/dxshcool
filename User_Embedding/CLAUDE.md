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
| VOD 영상 임베딩 | CLIP ViT-B/32 (`VOD_Embedding` 브랜치) | 512 | `vod_embedding` |
| VOD 메타데이터 임베딩 | paraphrase-multilingual-MiniLM-L12-v2 (`VOD_Embedding` 브랜치) | 384 | `vod_meta_embedding` (별도 테이블) |
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

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| VOD 결합 임베딩 로더 | `src/vod_embedding_loader.py` |
| 유저 임베딩 생성 | `src/user_embedder.py` |
| watch_history 데이터 로더 | `src/data_loader.py` |
| DB 연결 헬퍼 | `src/db.py` |
| 임베딩 생성 + 적재 실행 | `scripts/run_embed.py` |
| pytest | `tests/test_data_loader.py`, `test_user_embedder.py`, `test_vod_loader.py` |
| 파이프라인 설정 | `config/embed_config.yaml` |

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
- **멱등성**: `ON CONFLICT (user_id_fk) DO UPDATE SET embedding = EXCLUDED.embedding, vod_count = EXCLUDED.vod_count, updated_at = NOW()`
- **최소 시청 조건**: 시청 VOD가 1건 이상 + 결합 임베딩이 DB에 존재하는 경우만 생성

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` User_Embedding 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.watch_history` | `user_id_fk`, `vod_id_fk`, `completion_rate` | VARCHAR(64), VARCHAR(64), REAL | 가중 평균 가중치 |
| `public.vod_embedding` | `vod_id_fk`, `embedding` | VARCHAR(64), VECTOR(512) | CLIP 파트 |
| `public.vod_meta_embedding` | `vod_id_fk`, `embedding` | VARCHAR(64), VECTOR(384) | METADATA 파트 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.user_embedding` | `user_id_fk` | VARCHAR(64) | ON CONFLICT 기준 (UNIQUE) |
| `public.user_embedding` | `embedding` | VECTOR(896) | L2 정규화 후 concat(CLIP 512 + META 384) |
| `public.user_embedding` | `vod_count` | INTEGER | 임베딩 생성에 사용된 고유 VOD 수 |
| `public.user_embedding` | `model_name` | VARCHAR(100) | `'weighted_mean'` |
