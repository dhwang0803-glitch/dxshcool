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

스키마 상세 → `schemas/` SQL 파일 참조. 브랜치별 읽기/쓰기 컬럼 → `docs/DEPENDENCY_MAP.md` 참조.

### Silver 계층 (public 스키마)

| 테이블 | 설명 |
|--------|------|
| `public.vod` | VOD 메타데이터 (166,159건) |
| `public.vod_embedding` | VOD CLIP 512차원 벡터 (pgvector) |
| `public.vod_meta_embedding` | VOD 메타데이터 384차원 벡터 (pgvector) |
| `public.user_embedding` | 사용자 행동 벡터 896차원 (CLIP 512 + META 384, pgvector) |
| `public.watch_history` | 시청 이력 — 주별 파티셔닝 |
| `public.detected_objects` | 사물인식 결과 (Shopping_Ad 입력) |
| `public.tv_schedule` | TV 실시간 시간표 (EPG) |

### Gold 계층 (serving 스키마)

| 테이블/MV | 설명 |
|-----------|------|
| `serving.vod_recommendation` | 사용자별 추천 결과 캐시 (TTL 7일) |
| `serving.mv_vod_watch_stats` | VOD별 시청 통계 MV |
| `serving.mv_age_grp_vod_stats` | 연령대별 선호 VOD MV |
| `serving.mv_daily_watch_stats` | 일별 시청 통계 MV |

## 인터페이스

**다운스트림**: RAG, VOD_Embedding, Poster_Collection, User_Embedding, CF_Engine, Vector_Search, Object_Detection, Shopping_Ad, API_Server 모두 이 스키마를 참조.

공지 대상 브랜치 판단 → `docs/DEPENDENCY_MAP.md` 에서 변경 테이블의 소비 브랜치 조회.

---

## Rule 2 — 마이그레이션 공지 의무 (MANDATORY)

마이그레이션 추가 시 **커밋과 동일 세션**에서 수행한다.

```
migrations/YYYYMMDD_*.sql 작성 →
  docs/DEPENDENCY_MAP.md 에서 변경 테이블의 "소비 브랜치" 목록 조회 →
    해당 브랜치 CLAUDE.md 인터페이스 섹션을 컬럼/타입 수준으로 수정 →
      PR 설명에 공지 대상 브랜치 명시
```

**공지 생략 조건**: 소비 브랜치가 없는 신규 테이블 추가만 해당.
**공지 대상 조회 기준**: `docs/DEPENDENCY_MAP.md` — 변경 없이 구 문서 참조 금지.

---

## Rule 4 — DEPENDENCY_MAP 등록 의무 (MANDATORY)

새 브랜치 생성 시 **첫 커밋 전**에 `docs/DEPENDENCY_MAP.md` 를 수정한다.

1. 읽는 테이블 → 해당 행 "소비 브랜치"에 추가
2. 쓰는 테이블 → 해당 행 "생산 브랜치"에 추가
3. 새 테이블 필요 시 → Database_Design과 협의 후 행 추가
4. 브랜치별 컬럼 상세 섹션에 명세 추가

**등록 없이 DB 연동 코드 작성 금지.**

자세한 절차 → `docs/DEPENDENCY_MAP.md` 하단 "새 브랜치 등록 절차" 참조.

---

## 마이그레이션 파일 네이밍

```
migrations/
├── 20260308_add_rag_columns.sql
├── 20260309_add_cast_lead_cast_guest.sql
└── 20260311_add_user_embedding_table.sql
```

---

## 🤝 협업 규칙 (루트 CLAUDE.md 전문 참조)

- **직접 Push 금지** — 반드시 PR을 통해 병합
- **PR description 필수 항목**:
  1. 변경사항 요약
  2. 사후영향 평가 (`agents/IMPACT_ASSESSOR.md` 실행 결과) — **DB는 모든 레이어의 기반이므로 특히 중요**
  3. 보안 점검 보고서 (`agents/SECURITY_AUDITOR.md` 실행 결과)
- PR 템플릿: `.github/pull_request_template.md`

> ⚠️ DB 스키마 변경(ALTER/DROP)은 리스크 등급 🔴 HIGH 이상.
> 반드시 마이그레이션 DOWN 스크립트 포함 후 PR 제출.
