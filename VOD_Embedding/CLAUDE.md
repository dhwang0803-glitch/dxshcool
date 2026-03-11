# VOD_Embedding — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

이 브랜치는 임베딩을 **두 가지** 방식으로 생성한다.

| 임베딩 종류 | 입력 | 모델 | 차원 | 주요 파일 |
|------------|------|------|------|-----------|
| 영상 임베딩 | YouTube 트레일러 프레임 | CLIP ViT-B/32 | 512 | `src/embedder.py` (예정) |
| 메타데이터 임베딩 | 제목/장르/감독/출연/줄거리 | paraphrase-multilingual-MiniLM-L12-v2 | 384 | `src/meta_embedder.py` |

메타데이터 임베딩은 DB 쓰기 권한 제한으로 Parquet 파일로 먼저 저장 후 `ingest_to_db.py`로 적재한다.
영상 임베딩은 `vod_embedding` 테이블에 저장된다.

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

| 파일 종류 | 저장 위치 | 상태 |
|-----------|-----------|------|
| 메타데이터 임베딩 파이프라인 | `src/meta_embedder.py` | ✅ 완료 |
| DB 연결 헬퍼 | `src/db.py` | ✅ 완료 |
| 임베딩 설정 | `src/config.py` | ✅ 완료 |
| 메타 임베딩 → Parquet 실행 스크립트 | `scripts/run_meta_embed_parquet.py` | ✅ 완료 (산출물: data/vod_meta_embedding_20260311.parquet, 166,159건, 102.3MB) |
| 영상 임베딩 모델 로드/추론 | `src/embedder.py` | 🔲 예정 |
| 팀 분할 파일 생성 스크립트 | `scripts/split_tasks.py` | ✅ 완료 |
| 트레일러 수집 스크립트 | `scripts/crawl_trailers.py` | 🔄 실행 중 (tasks_A.json, 381번~) |
| 배치 영상 임베딩 스크립트 | `scripts/batch_embed.py` | 🔲 예정 |
| DB 적재 스크립트 | `scripts/ingest_to_db.py` | 🔲 예정 (vod_meta_embedding 테이블 생성 후) |
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

- 영상 임베딩 저장 테이블: `vod_embedding` (pgvector, `<=>` 코사인 거리 인덱스)
- 메타데이터 임베딩 저장 테이블: `vod_meta_embedding` (DB 생성 전까지 Parquet으로 보관)
- 멱등성: `ON CONFLICT (vod_id_fk, embedding_type) DO UPDATE`

## ⚠️ 알려진 이슈 / 현황

- `vod` 테이블에 `is_active` 컬럼 없음 → `run_meta_embed_parquet.py`는 WHERE 조건 제거로 우회
- `vod_meta_embedding` 테이블 미생성 (조장 담당) → 생성 후 `ingest_to_db.py`로 Parquet 적재 필요
- 메타데이터 임베딩 산출물: `data/vod_meta_embedding_20260311.parquet` (166,159건, 102.3MB) ✅ 검증 완료

## 팀 분할 실행 명령

### 오너 (1회)
```bash
# 4명 분할 파일 생성
python scripts/split_tasks.py
# → data/tasks_A.json  (~9,570건,  TV 연예/오락 앞 절반)
# → data/tasks_B.json  (~9,571건,  TV 연예/오락 뒤 절반)
# → data/tasks_C.json  (~11,508건, 영화 + TV드라마 + 키즈)
# → data/tasks_D.json  (~11,102건, TV애니메이션 + TV 시사/교양 + 기타 등)
```

### 팀원 (각자 담당 X = A/B/C/D)
```bash
# 1. 트레일러 다운로드
python scripts/crawl_trailers.py --task-file data/tasks_X.json

# 2. CLIP 임베딩 → parquet
python scripts/batch_embed.py --output parquet \
    --out-file data/embeddings_이름.parquet \
    --delete-after-embed

# 진행 상황 확인
python scripts/crawl_trailers.py --status
python scripts/batch_embed.py --status
```

## 인터페이스

- **업스트림**: `Database_Design` — `vod_embedding`, `vod_meta_embedding` 테이블 스키마
- **다운스트림**: `Vector_Search` — 이 모듈이 생성한 벡터를 쿼리하여 유사 콘텐츠 검색
- **산출물 전달**: `data/vod_meta_embedding_20260311.parquet` → 조장에게 전달 후 DB 적재
