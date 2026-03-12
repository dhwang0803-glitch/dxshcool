# VOD Recommendation — Claude Code 프로젝트 규칙

모든 브랜치 공통 지침. 브랜치별 CLAUDE.md가 있으면 이 파일과 함께 적용된다.

---

## 프로젝트 개요

IPTV/케이블 VOD 콘텐츠를 대상으로 한 **지능형 추천·광고 시스템** 풀스택 구현.

| 레이어 | 설명 |
|--------|------|
| 데이터 인프라 | PostgreSQL + pgvector, 메타데이터 자동수집 (TMDB/KMDB/Naver/JustWatch), 시리즈 포스터 수집, 사용자 행동 벡터 임베딩 |
| ML 추천 엔진 | 행렬 분해(CF) + 벡터 유사도 2종 (콘텐츠 기반 + 영상 임베딩) |
| 영상 AI | CLIP 임베딩, 실시간 사물인식 |
| 광고 시스템 | TV 실시간 시간표 + 사물인식 → 유사 홈쇼핑 상품 팝업 |
| 서비스 레이어 | FastAPI 백엔드 + React/Next.js 프론트엔드 |

상세 로드맵 → [`docs/ROADMAP.md`](docs/ROADMAP.md)

---

## 브랜치 구조

### Phase 1 — 데이터 인프라 (진행 중)

| 브랜치 | 역할 | 주요 경로 |
|--------|------|-----------|
| `main` | 공통 설정, 문서, 에이전트 템플릿 | `.claude/`, `_agent_templates/`, `docs/` |
| `Database_Design` | PostgreSQL 스키마 + 마이그레이션 | `Database_Design/schemas/`, `migrations/` |
| `RAG` | 메타데이터 결측치 자동수집 파이프라인 | `RAG/src/`, `RAG/scripts/` |
| `VOD_Embedding` | CLIP 영상 임베딩(512) + 메타데이터 임베딩(384) 파이프라인 | `VOD_Embedding/src/`, `VOD_Embedding/scripts/` |
| `Poster_Collection` | Naver 포스터 수집 → 로컬 저장 → DB `poster_url` 적재 | `Poster_Collection/src/`, `Poster_Collection/scripts/` |
| `User_Embedding` | VOD 결합 임베딩(512+384=896차원) 기반 ALS 행렬분해 → `user_embedding` 적재 | `User_Embedding/src/`, `User_Embedding/scripts/` |

### Phase 2 — 추천 엔진

| 브랜치 | 역할 |
|--------|------|
| `CF_Engine` | 행렬 분해 기반 협업 필터링 추천 엔진 |
| `Vector_Search` | 벡터 유사도 검색 엔진 (콘텐츠 기반 + 임베딩 기반) |

### Phase 3 — 영상 AI

| 브랜치 | 역할 |
|--------|------|
| `Object_Detection` | 영상 실시간 사물인식 (YOLO/Detectron2) |
| `Shopping_Ad` | 사물인식 결과 → TV 시간표 연동 → 홈쇼핑 팝업 광고 출력 |

### Phase 4 — 서비스 레이어

| 브랜치 | 역할 |
|--------|------|
| `API_Server` | FastAPI 백엔드 (추천/검색/광고 엔드포인트) |
| `Frontend` | React/Next.js 클라이언트 (시청자 UI + 광고 팝업) |

---

## 폴더 구조 컨벤션 (전 브랜치 통일)

### ML/데이터 파이프라인 모듈

```
{Module}/
├── src/          ← import되는 라이브러리 (직접 실행 X)
├── scripts/      ← 직접 실행 스크립트 (python scripts/run_xxx.py)
├── tests/        ← pytest
├── config/       ← yaml, .env.example
└── docs/         ← 설계 문서, 파일럿 리포트
```

### API 서버 (FastAPI)

```
API_Server/
├── app/
│   ├── routers/      ← 엔드포인트별 라우터
│   ├── services/     ← 비즈니스 로직
│   ├── models/       ← Pydantic 스키마
│   └── main.py
├── tests/
└── config/
```

### 프론트엔드 (React/Next.js)

```
Frontend/
├── src/
│   ├── components/
│   ├── pages/
│   └── services/     ← API 클라이언트
├── public/
└── tests/
```

### 규칙 요약

| 폴더 | 용도 |
|------|------|
| `src/` | `import`되는 모듈. 직접 실행 X |
| `scripts/` | `python scripts/run_xxx.py`로 실행 |
| `tests/` | pytest. `scripts/`는 테스트 대상 아님 |
| `config/` | `.yaml`, `.env.example` (실제 `.env` 제외) |
| `docs/` | 설계 문서, 파일럿 결과 리포트 |

---

## 프로젝트 개요 (Database_Design 브랜치)

- **프로젝트**: VOD 추천 시스템 PostgreSQL 데이터베이스
- **DB**: PostgreSQL on VPC
- **접속 정보**: `.env` 파일 (Git 제외, 팀 내 별도 공유)

## 커밋 금지 파일

- `.env` — DB 접속 정보
- `.claude/settings.local.json` — Claude Code 로컬 설정 (자격증명 포함 가능)
- `data/` — CSV 원본 데이터 (대용량)

---

## 🗄️ DB 스키마 협업 규칙 (Rule 1 & Rule 3 — 모든 브랜치 적용)

### Rule 1 — DB 스키마 참조 규칙

**`Database_Design` 브랜치가 스키마 단일 진실 원천(SSoT)이다. 직접 기재 금지.**

**확인 순서:**
```
테이블/컬럼 정보가 필요할 때 →
  1순위: Database_Design/schemas/ SQL 파일 직접 확인
  2순위: Database_Design/docs/DEPENDENCY_MAP.md 컬럼 상세
  ← 둘 중 하나와 다른 내용이 CLAUDE.md/문서에 있으면 Database_Design 기준으로 즉시 수정
```

**신규 브랜치 생성 시 (DB 접근 코드 작성 전 필수):**
1. `Database_Design/docs/DEPENDENCY_MAP.md` 에 브랜치 등록 (→ Rule 4)
2. 브랜치 CLAUDE.md 인터페이스 섹션을 Rule 3 형식으로 작성

### Rule 3 — 인터페이스 섹션 표준화 형식

각 브랜치 CLAUDE.md의 **인터페이스** 섹션은 테이블·컬럼·타입 수준으로 명시한다.

```markdown
## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id`, `asset_nm` | VARCHAR(64), VARCHAR | 처리 대상 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.some_table` | `col_name` | TYPE | ON CONFLICT 기준 등 |
```

스키마 변경은 `Database_Design` 에 먼저 반영 후 이 섹션을 업데이트한다.
컬럼/타입이 불확실하면 `Database_Design/docs/DEPENDENCY_MAP.md` 를 기준으로 한다.

---

## 🔒 보안 규칙 (MANDATORY — 모든 브랜치 적용)

**파일 수정/생성 또는 git commit 전 반드시 검증한다.**

### 1. 하드코딩된 자격증명 금지

```python
# 절대 금지
TMDB_API_KEY = "abcd1234..."
DB_PASSWORD  = "mysecret"

# 올바른 방식
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DB_PASSWORD  = os.getenv("DB_PASSWORD")
```

### 2. os.getenv() 기본값에 실제 인프라 정보 금지

```python
# 절대 금지 — 실제 서버 IP, DB명, 사용자명 노출
host=os.getenv("DB_HOST", "10.0.0.1")
dbname=os.getenv("DB_NAME", "prod_db")
user=os.getenv("DB_USER", "dbadmin")

# 올바른 방식
host=os.getenv("DB_HOST")
dbname=os.getenv("DB_NAME")
user=os.getenv("DB_USER")
port=int(os.getenv("DB_PORT", "5432"))  # 공개 표준 포트는 허용
```

### 3. .env 파일 직접 읽기 금지
- `.env` 파일을 Read 도구로 읽지 않는다
- `.env` 내용을 대화창, 로그에 출력하지 않는다
- DB 비밀번호, API 키 실제 값을 응답 텍스트에 포함하지 않는다
- 자격증명이 필요한 경우 사용자가 직접 터미널에서 입력하도록 안내
- 새 자격증명 설정 시 `.env.example`만 제공하고 실제 값은 사용자가 직접 입력

### 4. DB 접속 명령어 작성 규칙

```bash
# 올바른 방식
set -a && source .env && set +a
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME

# 절대 금지
PGPASSWORD=실제비밀번호 psql -h 실제IP ...
```

### 5. .gitignore 확인
커밋 전 아래 파일이 .gitignore에 포함되어 있는지 확인:
- `.env`
- `*.pem`, `*.key`, `credentials.json`
- `.claude/settings.local.json`

### 6. Pre-commit 점검 절차
```
파일 수정 시 →
  Grep: "os.getenv\(.*," 패턴 스캔 →
    기본값에 실제 인프라 정보 있으면 즉시 제거 →
      commit 전 보안 점검 결과 명시적으로 보고
```

**위반 시**: 커밋 중단, 즉시 수정 후 재커밋
