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
| SBERT 인덱스 빌드 스크립트 | `scripts/build_index.py` |
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

- pgvector IVFFlat/HNSW 인덱스 (`<=>` 코사인 거리)
- SBERT 모델: `jhgan/ko-sroberta-multitask` (한국어)

## 앙상블 공식

```python
final_score = α * clip_score + (1 - α) * content_score
# α 초기값 = 0.4 (config/search_config.yaml에서 조정)
```

## 인터페이스

- **업스트림**: `VOD_Embedding` — clip_embeddings 테이블 (512차원 벡터)
- **업스트림**: `Database_Design` — vod 테이블 메타데이터 (장르, 감독, 배우)
- **다운스트림**: `API_Server` — `/similar/{asset_id}` 엔드포인트
