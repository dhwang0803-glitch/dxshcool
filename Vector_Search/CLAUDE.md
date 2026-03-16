# Vector_Search — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**벡터 유사도 기반 콘텐츠 추천 엔진 2종**을 구현한다.

| 엔진 | 입력 | 방법 |
|------|------|------|
| 콘텐츠 기반 | 메타데이터 (장르/감독/배우/줄거리) | SBERT 임베딩 + 코사인 유사도 |
| 영상 기반 | CLIP 512차원 벡터 | pgvector `<=>` 연산자 |

두 스코어를 앙상블하여 최종 유사 콘텐츠 순위를 생성한다.

## 파일 위치 규칙 (MANDATORY)

```
Vector_Search/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 앙상블 가중치 yaml
└── docs/      ← 실험 리포트
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 메타데이터 기반 유사도 | `src/content_based.py` |
| CLIP 임베딩 기반 유사도 | `src/clip_based.py` |
| 앙상블 로직 | `src/ensemble.py` |
| ~~SBERT 인덱스 빌드~~ | 불필요 — DB `vod_meta_embedding` 직접 검색 |
| 유사 콘텐츠 검색 스크립트 | `scripts/search.py` |
| 결과 DB 적재 | `scripts/export_to_db.py` |
| pytest | `tests/` |
| 앙상블 가중치 설정 | `config/search_config.yaml` |

**`Vector_Search/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
from sentence_transformers import SentenceTransformer  # 메타데이터 SBERT 임베딩
from pgvector.psycopg2 import register_vector          # CLIP 벡터 검색
import psycopg2
import numpy as np
```

- pgvector IVFFlat 인덱스 (`<=>` 코사인 거리)
- 메타 SBERT 모델: `paraphrase-multilingual-MiniLM-L12-v2` (384차원, VOD_Embedding 적재)
- CLIP 모델: `clip-ViT-B-32` (512차원, VOD_Embedding 적재)

## 앙상블 공식

```python
final_score = α * clip_score + (1 - α) * content_score
# α 초기값 = 0.4 (config/search_config.yaml에서 조정)
```

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod_embedding` | `vod_id_fk`, `embedding` | VARCHAR(64), VECTOR(512) | CLIP 유사도 검색 |
| `public.vod_meta_embedding` | `vod_id_fk`, `embedding` | VARCHAR(64), VECTOR(384) | 메타 유사도 검색 |
| `public.user_embedding` | `user_id_fk`, `embedding` | VARCHAR(64), VECTOR(896) | 개인화 검색 (추후) |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | - | `'VISUAL_SIMILARITY'` 고정, TTL 7일 |
