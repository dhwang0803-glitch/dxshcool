# Database_Design — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

PostgreSQL + pgvector 스키마 설계 및 마이그레이션 관리.
**모든 브랜치의 기반**이 되는 데이터 레이어. 스키마 변경 시 다른 팀과 사전 협의 필수.

## 파일 위치 규칙 (MANDATORY)

```
Database_Design/
├── schemas/      ← DDL (CREATE TABLE/INDEX/VIEW) SQL 파일
├── migrations/   ← 스키마 변경 이력 SQL (YYYYMMDD_설명.sql)
├── scripts/      ← Python 실행 스크립트 (migrate.py, validate.py 등)
├── tests/        ← pytest (DB 연결, 스키마 검증)
└── docs/         ← ERD, 설계 문서
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| `CREATE TABLE`, `CREATE INDEX` | `schemas/` |
| `ALTER TABLE`, 컬럼 추가/삭제 | `migrations/YYYYMMDD_*.sql` |
| Python DB 관리 스크립트 | `scripts/` |
| pytest | `tests/` |

**`Database_Design/` 루트 또는 프로젝트 루트에 파일 직접 생성 금지.**

## 기술 스택

```python
import psycopg2          # DB 연결
from pgvector.psycopg2 import register_vector  # 벡터 타입
import sqlalchemy        # ORM (선택)
```

- PostgreSQL 18 / pgvector 확장
- 벡터 컬럼: `vector(512)` (CLIP ViT-B/32 출력)
- 인덱스: IVFFlat 또는 HNSW (`<=>` 코사인 거리)

## 핵심 테이블

| 테이블 | 설명 |
|--------|------|
| `vod` | VOD 메타데이터 (166,159건) |
| `clip_embeddings` | CLIP 512차원 벡터 |
| `watch_history` | 시청 이력 (CF_Engine 입력) |
| `detected_objects` | 사물인식 결과 (Shopping_Ad 입력) |
| `tv_schedule` | TV 실시간 시간표 (EPG) |

## 인터페이스

- **다운스트림**: RAG, VOD_Embedding, CF_Engine, Vector_Search, Object_Detection, Shopping_Ad, API_Server 모두 이 스키마를 참조
- 스키마 변경 시 `migrations/` 에 이력 SQL 추가 후 다운스트림 브랜치에 공지

## 마이그레이션 파일 네이밍

```
migrations/
├── 20260308_add_rag_columns.sql
├── 20260309_add_cast_lead_cast_guest.sql
└── 20260310_create_clip_embeddings.sql
```
