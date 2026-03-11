# VOD_Embedding — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

이 브랜치는 임베딩을 **두 가지** 방식으로 생성한다.

| 임베딩 종류 | 입력 | 모델 | 차원 | 주요 파일 |
|------------|------|------|------|-----------|
| 영상 임베딩 | YouTube 트레일러 프레임 | CLIP ViT-B/32 | 512 | `src/embedder.py` (예정) |
| 메타데이터 임베딩 | 제목/장르/감독/출연/줄거리 | paraphrase-multilingual-MiniLM-L12-v2 | 384 | `src/meta_embedder.py` |

두 임베딩 모두 `vod_embedding` 테이블에 `embedding_type` 컬럼으로 구분하여 저장된다.

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
| 파일 종류 | 저장 위치 | 상태 |
|-----------|-----------|------|
| 메타데이터 임베딩 파이프라인 | `src/meta_embedder.py` | ✅ 완료 |
| DB 연결 헬퍼 | `src/db.py` | ✅ 완료 |
| 임베딩 설정 | `src/config.py` | ✅ 완료 |
| 메타 임베딩 실행 스크립트 | `scripts/run_meta_embed.py` | 🔲 예정 |
| 영상 임베딩 모델 로드/추론 | `src/embedder.py` | 🔲 예정 |
| 트레일러 수집 스크립트 | `scripts/crawl_trailers.py` | 🔲 예정 |
| 배치 영상 임베딩 스크립트 | `scripts/batch_embed.py` | 🔲 예정 |
| DB 적재 스크립트 | `scripts/ingest_to_db.py` | 🔲 예정 |
| pytest | `tests/` | 🔲 예정 |

**`VOD_Embedding/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
# 메타데이터 임베딩
from sentence_transformers import SentenceTransformer  # paraphrase-multilingual-MiniLM-L12-v2
import psycopg2

# 영상 임베딩 (예정)
import yt_dlp             # 트레일러 수집
import clip               # OpenAI CLIP ViT-B/32
import torch
import cv2                # 프레임 추출
from pgvector.psycopg2 import register_vector
```

## 임베딩 스펙

| 종류 | 모델 | 차원 | embedding_type 값 |
|------|------|------|-------------------|
| 메타데이터 | paraphrase-multilingual-MiniLM-L12-v2 | 384 | `"METADATA"` |
| 영상 (예정) | CLIP ViT-B/32 | 512 | `"CLIP"` (예정) |

- 저장 테이블: `vod_embedding`
- 저장 방식: pgvector `<=>` 코사인 거리 인덱스
- 멱등성: `ON CONFLICT (vod_id_fk, embedding_type) DO UPDATE`

## ⚠️ 알려진 이슈

- `meta_embedder.py`의 `fetch_all_vods()`가 `WHERE is_active = TRUE` 조건을 사용하나,
  현재 `vod` 테이블에 `is_active` 컬럼이 없음.
  실행 전 `Database_Design` 브랜치에서 컬럼 추가 마이그레이션 선행 필요.

## 인터페이스

- **업스트림**: `Database_Design` — `vod_embedding` 테이블 스키마, `vod.is_active` 컬럼
- **다운스트림**: `Vector_Search` — 이 모듈이 생성한 벡터를 쿼리하여 유사 콘텐츠 검색
