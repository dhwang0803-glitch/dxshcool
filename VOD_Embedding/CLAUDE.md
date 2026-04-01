# VOD_Embedding — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

VOD 임베딩을 **두 가지** 방식으로 생성하여 pgvector 테이블에 적재한다.

| 임베딩 종류 | 입력 | 모델 | 차원 | 저장 테이블 |
|------------|------|------|------|-------------|
| 영상 임베딩 | YouTube 트레일러 프레임 | CLIP ViT-B/32 | 512 | `public.vod_embedding` |
| 메타데이터 임베딩 | 제목/장르/감독/출연/줄거리 | paraphrase-multilingual-MiniLM-L12-v2 | 384 | `public.vod_meta_embedding` |
| 시리즈 대표 임베딩 | 대표 에피소드의 메타 임베딩 | (위와 동일) | 384 | `public.vod_series_embedding` |

## 파일 위치 규칙 (MANDATORY)

```
VOD_Embedding/
├── src/                ← import 전용 라이브러리 (직접 실행 X)
│   ├── config.py             # 임베딩 설정 (모델명, 차원, 경로)
│   ├── db.py                 # DB 연결 헬퍼
│   └── meta_embedder.py      # 메타데이터 임베딩 (paraphrase-multilingual-MiniLM-L12-v2)
├── scripts/            ← 직접 실행 스크립트
│   ├── crawl_trailers.py         # YouTube 트레일러 다운로드 (yt-dlp, --status 지원)
│   ├── batch_embed.py            # CLIP 영상 임베딩 → parquet (--status 지원)
│   ├── run_meta_embed_parquet.py # 메타 임베딩 → parquet (v2: 에피소드별 개별)
│   ├── ingest_to_db.py           # parquet → vod_embedding DB 적재 (--propagate 시리즈 전파)
│   ├── run_parallel_pipeline.py  # N분할 병렬 파이프라인 (crawl→embed→ingest→propagate)
│   └── progress_report.py        # 크롤링/임베딩 진행 현황 보고서
├── tests/              ← pytest (미구현)
├── config/             ← 설정 파일
└── docs/
    ├── plans/          ← PLAN_00~03 설계 문서
    └── reports/        ← 세션·파일럿·진행 리포트
```

**`VOD_Embedding/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
# 메타데이터 임베딩
from sentence_transformers import SentenceTransformer  # paraphrase-multilingual-MiniLM-L12-v2
import psycopg2

# 영상 임베딩
import yt_dlp             # 트레일러 수집
import clip               # OpenAI CLIP ViT-B/32
import torch
import cv2                # 프레임 추출
from pgvector.psycopg2 import register_vector
```

## 파이프라인 실행

```bash
# 1. 트레일러 다운로드
python VOD_Embedding/scripts/crawl_trailers.py --task-file data/tasks_X.json
python VOD_Embedding/scripts/crawl_trailers.py --status

# 2. CLIP 임베딩 → parquet
python VOD_Embedding/scripts/batch_embed.py --output parquet \
    --out-file data/embeddings_이름.parquet --delete-after-embed
python VOD_Embedding/scripts/batch_embed.py --status

# 3. 메타 임베딩 → parquet
python VOD_Embedding/scripts/run_meta_embed_parquet.py

# 4. DB 적재 (parquet → vod_embedding)
python VOD_Embedding/scripts/ingest_to_db.py                        # 전체 parquet
python VOD_Embedding/scripts/ingest_to_db.py --file data/xxx.parquet # 특정 파일
python VOD_Embedding/scripts/ingest_to_db.py --propagate             # 시리즈 전파
python VOD_Embedding/scripts/ingest_to_db.py --verify                # 검증

# 5. 병렬 파이프라인 (crawl→embed→ingest→propagate 일괄)
python VOD_Embedding/scripts/run_parallel_pipeline.py --task-file data/tasks_X.json
python VOD_Embedding/scripts/run_parallel_pipeline.py --task-file data/tasks_X.json --start-from embed

# 6. 진행 현황 보고서
python VOD_Embedding/scripts/progress_report.py
```

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
| `public.vod_series_embedding` | `series_nm` | VARCHAR(255) | UNIQUE, COALESCE(series_nm, asset_nm) |
| `public.vod_series_embedding` | `representative_vod_id` | VARCHAR(64) | FK → vod.full_asset_id |
| `public.vod_series_embedding` | `embedding` | VECTOR(384) | 대표 에피소드의 메타 임베딩 |
| `public.vod_series_embedding` | `ct_cl`, `poster_url` | VARCHAR(64)/TEXT | 서빙 편의 (JOIN 불필요) |
| `public.vod_series_embedding` | `episode_count` | INTEGER | 시리즈 에피소드 수 |

## 시리즈 전파 전략

```
시리즈 단위 ct_cl (TV드라마/TV애니메이션/키즈/TV시사교양/영화):
    대표 에피소드 1개 적재 후 --propagate로 같은 series_nm 전체에 복사

에피소드 단위 ct_cl (TV 연예/오락):
    각 에피소드 개별 적재, 전파 없음
```

---

**마지막 수정**: 2026-04-01
**프로젝트 상태**: 파이프라인 구현 완료, DB 적재 운영 중
