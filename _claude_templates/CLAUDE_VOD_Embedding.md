# VOD_Embedding — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

YouTube 트레일러 수집(yt-dlp) → CLIP ViT-B/32 영상 임베딩(512차원) → pgvector DB 적재.
Vector_Search의 영상 기반 유사도 검색의 기반 데이터를 생성한다.

## 파일 위치 규칙 (MANDATORY)

```
VOD_Embedding/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 설정 파일
└── docs/
    ├── plans/    ← PLAN_01~03 설계 문서
    └── reports/  ← 파일럿 결과 리포트
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 임베딩 모델 로드/추론 로직 | `src/embedder.py` |
| DB 연결/적재 로직 | `src/db_client.py` |
| 트레일러 수집 스크립트 | `scripts/crawl_trailers.py` |
| 배치 임베딩 스크립트 | `scripts/batch_embed.py` |
| DB 적재 스크립트 | `scripts/ingest_to_db.py` |
| pytest | `tests/` |

**`VOD_Embedding/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import yt_dlp             # 트레일러 수집
import clip               # OpenAI CLIP ViT-B/32
import torch
import cv2                # 프레임 추출
import psycopg2
from pgvector.psycopg2 import register_vector
```

## 임베딩 스펙

- 모델: CLIP ViT-B/32
- 출력: 512차원 float32 벡터
- DB 테이블: `vod_embedding.embedding vector(512)`
- 저장: pgvector `<=>` 코사인 거리 인덱스 (Milvus 미사용 — 인프라 단순화 결정)

## 인터페이스

- **업스트림**: `Database_Design` — vod_embedding 테이블 스키마
- **다운스트림**: `Vector_Search` — 이 모듈이 생성한 512차원 벡터를 쿼리하여 유사 콘텐츠 검색
