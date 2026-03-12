# VOD Recommendation System

IPTV/케이블 VOD 콘텐츠 대상 **지능형 추천·광고 시스템** 풀스택 구현 프로젝트.

상세 로드맵 → [`docs/ROADMAP.md`](docs/ROADMAP.md)

---

## 브랜치 구조

각 브랜치는 독립 모듈이며, 브랜치명 = 작업 디렉터리명.

### Phase 1 — 데이터 인프라

| 브랜치 | 역할 |
|--------|------|
| `Database_Design` | PostgreSQL 스키마 설계 + 마이그레이션 관리 |
| `RAG` | VOD 메타데이터 결측치 자동수집 (TMDB/KMDB/Naver/JustWatch) |
| `VOD_Embedding` | YouTube 트레일러 수집 → CLIP ViT-B/32 임베딩 → pgvector 적재 |
| `Poster_Collection` | Naver 포스터 수집 → 로컬 저장 → DB `poster_url` 적재 |

### Phase 2 — 추천 엔진

| 브랜치 | 역할 |
|--------|------|
| `CF_Engine` | 행렬 분해(ALS/SVD++) 기반 협업 필터링 추천 |
| `Vector_Search` | 콘텐츠 기반 + CLIP 임베딩 기반 유사도 검색 앙상블 |

### Phase 3 — 영상 AI

| 브랜치 | 역할 |
|--------|------|
| `Object_Detection` | YOLO/Detectron2 실시간 사물인식 |
| `Shopping_Ad` | 사물인식 결과 + TV EPG → 홈쇼핑 팝업 광고 |

### Phase 4 — 서비스 레이어

| 브랜치 | 역할 |
|--------|------|
| `API_Server` | FastAPI 백엔드 (추천/검색/광고 엔드포인트) |
| `Frontend` | React/Next.js 클라이언트 (VOD UI + 광고 팝업) |

---

## 시작 방법

```bash
# 1. 클론
git clone https://github.com/dhwang0803-glitch/dxshcool.git
cd dxshcool

# 2. git hooks 설정 (post-checkout 자동 스캐폴딩)
git config core.hooksPath .githooks

# 3. 환경변수 설정
cp .env.example .env
# .env에 실제 값 입력 (관리자에게 문의)

# 4. 브랜치 체크아웃 (자동으로 agents/, 폴더 구조, CLAUDE.md 생성됨)
git checkout <브랜치명>

# 5. Claude Code 세션 초기화
/init
```

---

## 협업 규칙

- `main` 브랜치 직접 Push **금지** — 반드시 Pull Request
- PR description 필수 항목:
  1. 변경사항 요약
  2. 사후영향 평가 (IMPACT_ASSESSOR 에이전트 실행 결과)
  3. 보안 점검 보고서 (SECURITY_AUDITOR 에이전트 실행 결과)
- PR 템플릿: `.github/pull_request_template.md`

---

## 보안 규칙 요약

- 하드코딩된 자격증명·IP·DB명 **절대 금지** — `os.getenv()` 사용
- `.env` 파일 git 커밋 금지 (`.gitignore` 포함됨)
- 상세 규칙: 루트 `CLAUDE.md` 보안 규칙 섹션 참고
