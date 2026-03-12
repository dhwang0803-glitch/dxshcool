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
- DB 컬럼: `clip_embeddings.embedding vector(512)`
- 저장: pgvector `<=>` 코사인 거리 인덱스

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` VOD_Embedding 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id`, `asset_nm`, `genre`, `director`, `cast_lead`, `smry` | 각종 VARCHAR/TEXT | 메타 임베딩 입력 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.vod_embedding` | `vod_id_fk` | VARCHAR(64) | UNIQUE |
| `public.vod_embedding` | `embedding` | VECTOR(512) | CLIP ViT-B/32 |
| `public.vod_embedding` | `embedding_type` | VARCHAR(32) | 허용값: `'CLIP'` |
| `public.vod_embedding` | `model_name`, `model_version` | VARCHAR | `'clip-ViT-B-32'` |
| `public.vod_embedding` | `frame_count` | SMALLINT | 기본 10 |
| `public.vod_embedding` | `source_type` | VARCHAR(32) | 허용값: `'TRAILER'`,`'FULL'` |
| `public.vod_meta_embedding` | `vod_id_fk` | VARCHAR(64) | UNIQUE |
| `public.vod_meta_embedding` | `embedding` | VECTOR(384) | paraphrase-multilingual-MiniLM-L12-v2 |
| `public.vod_meta_embedding` | `input_text` | TEXT | 결합 텍스트 (선택) |
| `public.vod_meta_embedding` | `source_fields` | TEXT[] | 기본: `['asset_nm','genre','director','cast_lead','smry']` |
