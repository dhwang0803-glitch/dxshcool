# VOD Recommendation System

IPTV/케이블 VOD 콘텐츠 대상 **지능형 추천 + 광고 시스템** 풀스택 구현 프로젝트.

---

## 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│          React/Next.js — 시청자 UI + 광고 팝업              │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                       API_Server                            │
│         FastAPI — 추천 / 검색 / 광고 엔드포인트             │
│         Cloud Run (dev: vod-api-dev / prod: vod-api)        │
└────┬──────────────┬──────────────┬──────────────────────────┘
     │              │              │
     ▼              ▼              ▼
┌─────────┐  ┌────────────┐  ┌──────────────┐
│CF_Engine│  │Vector_     │  │Shopping_Ad   │
│행렬분해  │  │Search      │  │지자체 광고   │
│추천엔진  │  │유사도검색  │  │+제철장터    │
└────┬────┘  └─────┬──────┘  └──────┬───────┘
     │              │                │
     └──────────────┼────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│          VPC PostgreSQL + pgvector (thin serving layer)      │
│  vod / vod_embedding(512) / vod_meta_embedding(384)         │
│  user_embedding(896) / serving.* (추천·광고 Gold 테이블)    │
└───────────┬──────────────────────────────────────────────────┘
            │ 데이터 공급 (로컬 연산 → VPC 적재)
┌───────────▼──────────────────────────────────────────────────┐
│              데이터 파이프라인 (로컬 연산)                    │
│   RAG (메타데이터)  ·  VOD_Embedding (CLIP 512 + 메타 384)  │
│   User_Embedding (ALS 행렬분해, 896차원)                     │
│   Poster_Collection (TMDB/Tving 포스터)                      │
│   Object_Detection (YOLO/CLIP/STT 배치 → parquet)           │
└──────────────────────────────────────────────────────────────┘
```

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| DB | PostgreSQL + pgvector (VPC) |
| 백엔드 | FastAPI, asyncpg, JWT (python-jose) |
| 프론트엔드 | React / Next.js |
| ML/추천 | ALS 행렬분해, 코사인 유사도 (pgvector `<=>`), K-Means 세그먼트 |
| 영상 AI | CLIP ViT-B/32 (임베딩+개념태깅), YOLOv8 (사물인식), Whisper (STT) |
| 임베딩 | paraphrase-multilingual-MiniLM-L12-v2 (메타 384D), CLIP (영상 512D) |
| 배포 | Google Cloud Run (dev/prod 분리), Docker |
| 실시간 | PG LISTEN/NOTIFY + 인메모리 버퍼 (Redis 미도입, 인프라 제약) |

---

## 브랜치 구조

각 브랜치는 독립 모듈이며, 브랜치명 = 작업 디렉터리명.

### Phase 1 — 데이터 인프라

| 브랜치 | 역할 | 상태 |
|--------|------|------|
| `Database_Design` | PostgreSQL 스키마 설계 + 마이그레이션 (28개) | 운영 중 |
| `RAG` | VOD 메타데이터 결측치 자동수집 (TMDB/KMDB/Naver/JustWatch) | 운영 중 |
| `VOD_Embedding` | YouTube 트레일러 CLIP 임베딩(512D) + 메타데이터 임베딩(384D) | 운영 중 |
| `Poster_Collection` | TMDB/Tving 포스터·백드롭 수집 → DB `poster_url` 적재 | 운영 중 |
| `User_Embedding` | VOD 결합 벡터(896D) 기반 ALS 행렬분해 → `user_embedding` 적재 | 구현 완료 |

### Phase 2 — 추천 엔진

| 브랜치 | 역할 | 상태 |
|--------|------|------|
| `CF_Engine` | ALS 기반 협업 필터링 → `serving.vod_recommendation` 적재 | 구현 완료 |
| `Vector_Search` | 메타+영상 벡터 유사도 앙상블 → `serving.vod_recommendation` 적재 | 구현 완료 |
| `Hybrid_Layer` | CF+Vector 후보 리랭킹 + 설명 가능한 추천 (태그 기반) | 구현 완료 |
| `gen_rec_sentence` | 유저 세그먼트별 맞춤 추천 문구 생성 → `serving.rec_sentence` | 구현 완료 |

### Phase 3 — 영상 AI

| 브랜치 | 역할 | 상태 |
|--------|------|------|
| `Object_Detection` | YOLO/CLIP/STT 3종 배치 인식 → parquet 산출물 (로컬 전용) | 구현 완료 |
| `Shopping_Ad` | 음식→제철장터 채널 연계 / 관광지→지자체 광고 팝업 | 구현 완료 |

### Phase 4 — 서비스 레이어

| 브랜치 | 역할 | 상태 |
|--------|------|------|
| `API_Server` | FastAPI 백엔드 (추천/검색/광고/구매/알림 26개 엔드포인트) | 배포 완료 |
| `Frontend` | React/Next.js 클라이언트 (VOD UI + 광고 팝업) | 개발 중 |

---

## 주요 기능

### 추천 시스템
- **협업 필터링**: ALS 행렬분해 기반 유저-아이템 추천
- **콘텐츠 기반**: 메타데이터(384D) + 영상(512D) 벡터 유사도 검색
- **하이브리드 리랭킹**: CF + Vector 후보를 태그 친화도로 리랭킹 + 설명 문구 생성
- **세그먼트별 추천 문구**: K-Means 유저 클러스터 × VOD별 맞춤 문구

### 홈 화면 배너
- **1단 개인화**: 유저 임베딩 기반 벡터 유사도 top 5
- **2단 인기**: 연령대별 인기 VOD top 5
- **3단 하이브리드**: hybrid_recommendation top 10

### 검색
- **통합 검색**: pg_trgm 유사도 검색 (제목/출연진/감독/장르)
- **초성 검색**: 한글 초성 prefix 매칭

### 광고 시스템
- **지자체 광고**: VOD 관광지/지역 장면 인식 → 지역 축제·관광 팝업
- **제철장터 연계**: VOD 음식 장면 인식 → 제철장터 채널 이동/시청예약

### 실시간 처리
- 시청 진행률: 인메모리 버퍼 → 60초 batch UPSERT
- 마이페이지 갱신: PG LISTEN/NOTIFY → WebSocket push
- 포인트 잔액: DB 트리거 자동 갱신
- 시청예약 알림: 30초 주기 background task

---

## 폴더 구조

### ML/데이터 파이프라인 모듈 (공통)

```
{Module}/
├── src/          ← import되는 라이브러리 (직접 실행 X)
├── scripts/      ← 직접 실행 스크립트 (python scripts/run_xxx.py)
├── tests/        ← pytest
├── config/       ← yaml, .env.example
└── docs/         ← 설계 문서, 리포트
```

### API 서버

```
API_Server/
├── app/
│   ├── routers/      ← 엔드포인트별 라우터
│   ├── services/     ← BaseService 기반 비즈니스 로직 (클래스 구조)
│   ├── models/       ← Pydantic 요청/응답 스키마
│   └── main.py       ← FastAPI 앱 진입점
├── tests/            ← pytest (39 tests, httpx AsyncClient)
└── config/
```

---

## 시작 방법

```bash
# 1. 클론
git clone https://github.com/dhwang0803-glitch/dxshcool.git
cd dxshcool

# 2. 환경 설정
conda activate myenv          # Python 3.12
pip install -r requirements.txt

# 3. 환경변수 설정
cp .env.example .env
# .env에 실제 값 입력 (관리자에게 문의)

# 4. 브랜치 체크아웃
git checkout <브랜치명>

# 5. API 서버 실행 (API_Server 브랜치)
cd API_Server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 배포

| 환경 | 서비스 | 소스 브랜치 |
|------|--------|-----------|
| 개발 | `vod-api-dev` (Cloud Run) | `main` |
| 운영 | `vod-api` (Cloud Run) | `release` |

배포 상세 → [`docs/DEPLOY_GUIDE.md`](docs/DEPLOY_GUIDE.md)

---

## 협업 규칙

- `main` 브랜치 직접 Push **금지** — 반드시 Pull Request
- 각 브랜치는 자기 폴더 내 파일만 커밋 (다른 브랜치 폴더 수정 금지)
- 운영 배포는 조장 승인 후에만 가능
- DB 스키마 변경은 `Database_Design` 브랜치에서 먼저 반영

---

## 보안 규칙

- 하드코딩된 자격증명·IP·DB명 **절대 금지** — `os.getenv()` 사용
- `.env` 파일 git 커밋 금지 (`.gitignore` 포함됨)
- 커밋 금지 파일: `.env`, `data/`, `*.parquet`, `*.pkl`, `*.pem`, `credentials.json`
- 상세 규칙: 루트 [`CLAUDE.md`](CLAUDE.md) 보안 규칙 섹션 참고

---

## 문서

| 문서 | 설명 |
|------|------|
| [`docs/ROADMAP.md`](docs/ROADMAP.md) | 전체 개발 로드맵 + 데이터 플로우 |
| [`docs/DEPLOY_GUIDE.md`](docs/DEPLOY_GUIDE.md) | Cloud Run 배포 가이드 |
| [`Database_Design/docs/DEPENDENCY_MAP.md`](Database_Design/docs/DEPENDENCY_MAP.md) | DB 테이블 × 브랜치 의존성 맵 |
| 각 브랜치 `CLAUDE.md` | 브랜치별 지침 + Rule 3 인터페이스 명세 |
