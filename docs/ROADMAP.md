# VOD Recommendation — 전체 개발 로드맵

> 최종 목표: IPTV/케이블 VOD 콘텐츠 지능형 추천·광고 시스템 풀스택 구현

---

## 시스템 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│          React/Next.js — 시청자 UI + 광고 팝업              │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                       API_Server                            │
│         FastAPI — 추천 / 검색 / 광고 엔드포인트             │
└────┬──────────────┬──────────────┬──────────────────────────┘
     │              │              │
     ▼              ▼              ▼
┌─────────┐  ┌────────────┐  ┌──────────────┐
│CF_Engine│  │Vector_     │  │Shopping_Ad   │
│행렬분해  │  │Search      │  │홈쇼핑 팝업   │
│추천엔진  │  │유사도검색  │  │광고 시스템   │
└────┬────┘  └─────┬──────┘  └──────┬───────┘
     │              │                │
     └──────────────┼────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│                  PostgreSQL + pgvector                       │
│  vod 테이블(+poster_url) / clip_embeddings / cf_matrix / tv_schedule │
└───────────┬──────────────────────────────────────────────────┘
            │ 데이터 공급
┌───────────▼──────────────────────────────────────────────────┐
│              데이터 파이프라인                                │
│   RAG (메타데이터)  ·  VOD_Embedding (CLIP)                  │
│   Poster_Collection (포스터)  ·  Object_Detection (사물인식) │
└──────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — 데이터 인프라 `진행 중`

### `Database_Design`
- PostgreSQL 스키마 설계 (vod, clip_embeddings, cf_matrix 등)
- pgvector 확장 설정
- 마이그레이션 이력 관리

**폴더 구조:**
```
Database_Design/
├── schemas/       ← DDL SQL 파일
├── migrations/    ← ALTER TABLE 이력 (날짜_설명.sql)
└── docs/          ← ERD, 설계 문서
```

---

### `RAG`
- 166,159건 VOD 메타데이터 결측치 자동수집
- 소스: TMDB → KMDB → JustWatch → Naver → 영상물등급위원회
- 대상 컬럼: director, cast_lead, cast_guest, rating, release_date, smry

**현황 (2026-03-11):**
| 컬럼 | 완성률 |
|------|--------|
| director | 92.5% |
| cast_lead | 72.0% |
| release_date | 74.9% |
| rating | 65.6% |
| cast_guest | 53.0% |

**폴더 구조:**
```
RAG/
├── src/           ← API 연동 라이브러리 (meta_sources, validation 등)
├── scripts/       ← 실행 파이프라인 (run_bulk_meta, run_naver_meta 등)
├── tests/
└── config/
```

---

### `VOD_Embedding`
- YouTube 트레일러 수집 (yt-dlp)
- CLIP ViT-B/32 영상 임베딩 → 512차원 벡터
- pgvector DB 적재

**현황 (파일럿 100건):**
- 크롤링 98%, 임베딩 78%, DB 적재 완료

**폴더 구조:**
```
VOD_Embedding/
├── src/           ← 임베딩 로직 라이브러리
├── scripts/       ← crawl_trailers, batch_embed, ingest_to_db
├── tests/
├── config/
├── plans/
└── reports/
```

---

### `Poster_Collection`
- Naver 이미지 검색 API로 시리즈별 포스터 URL 수집
- 이미지 다운로드 → 로컬 저장 → Google Drive로 DB 관리자에게 전달
- DB 관리자가 VPC에 업로드 후 `vod.poster_url` 컬럼 업데이트

**워크플로우:**
```
개발자: crawl_posters.py 실행
    → Naver API에서 series_nm 기반 포스터 URL 수집
    → 이미지 다운로드 → {LOCAL_POSTER_DIR}/{series_id}.jpg
    → export_manifest.py → manifest.csv 생성
    → Google Drive로 DB 관리자에게 전달

DB 관리자: (수동 작업)
    → VPC 서버에 이미지 업로드
    → update_poster_url.py 실행
    → vod 테이블 poster_url 컬럼 업데이트
```

**사전 조건:** `Database_Design` 브랜치에서 아래 마이그레이션 선행 필요
```sql
ALTER TABLE vod ADD COLUMN poster_url TEXT;
```

**폴더 구조:**
```
Poster_Collection/
├── src/           ← naver_poster, image_downloader, db_updater
├── scripts/       ← crawl_posters.py, export_manifest.py, update_poster_url.py
├── tests/
├── config/        ← poster_config.yaml
├── plans/
└── reports/
```

---

## Phase 2 — 추천 엔진

### `CF_Engine` — 협업 필터링 (행렬 분해)
- 시청 이력 기반 User-Item 행렬 구성
- ALS (Alternating Least Squares) 또는 SVD++ 적용
- 실시간 추천 결과 캐싱 (Redis 예정)

**예정 폴더 구조:**
```
CF_Engine/
├── src/           ← 행렬 분해 알고리즘, 데이터 로더
├── scripts/       ← train.py, evaluate.py, export_to_db.py
├── tests/
└── config/
```

---

### `Vector_Search` — 벡터 유사도 검색 (2종)
- **콘텐츠 기반**: 메타데이터(장르/감독/배우) TF-IDF 또는 SBERT 임베딩
- **영상 기반**: CLIP 임베딩 코사인 유사도 (pgvector `<=>` 연산자)
- 두 스코어 앙상블 → 최종 유사도 순위

**예정 폴더 구조:**
```
Vector_Search/
├── src/
│   ├── content_based.py   ← 메타데이터 기반 유사도
│   └── clip_based.py      ← 영상 임베딩 기반 유사도
├── scripts/
├── tests/
└── config/
```

---

## Phase 3 — 영상 AI

### `Object_Detection` — 영상 실시간 사물인식
- 모델: YOLO v8 또는 Detectron2
- 입력: TV 방송/VOD 영상 프레임
- 출력: 감지된 객체 레이블 + 신뢰도 + 바운딩박스
- DB 저장: `detected_objects` 테이블

**예정 폴더 구조:**
```
Object_Detection/
├── src/           ← 모델 로드, 프레임 추출, 추론 로직
├── scripts/       ← run_detection.py, batch_process.py
├── tests/
└── config/
```

---

### `Shopping_Ad` — 홈쇼핑 광고 팝업 시스템
- TV 실시간 시간표 수집 (EPG 파싱)
- Object_Detection 결과 → 유사 홈쇼핑 상품 매핑
- 시청 중 팝업: 상품 링크 or 채널 이동 or 시청예약

**데이터 플로우:**
```
TV 방송 프레임
    → Object_Detection (사물 감지)
    → 상품 카테고리 매핑 테이블
    → 홈쇼핑 채널 EPG 매칭
    → 팝업 메시지 생성 → API_Server → Frontend
```

**예정 폴더 구조:**
```
Shopping_Ad/
├── src/           ← epg_parser, product_mapper, popup_builder
├── scripts/       ← run_epg_sync.py, run_ad_pipeline.py
├── tests/
└── config/
```

---

## Phase 4 — 서비스 레이어

### `API_Server` — FastAPI 백엔드
- 추천 엔드포인트: `/recommend/{user_id}`
- 유사 콘텐츠: `/similar/{asset_id}`
- 광고 트리거: `/ad/popup` (WebSocket 또는 SSE)
- 인증: JWT

**예정 폴더 구조:**
```
API_Server/
├── app/
│   ├── routers/       ← recommend.py, search.py, ad.py, auth.py
│   ├── services/      ← 비즈니스 로직 (CF_Engine, Vector_Search 호출)
│   ├── models/        ← Pydantic 요청/응답 스키마
│   └── main.py
├── tests/
└── config/
```

---

### `Frontend` — React/Next.js 클라이언트
- VOD 목록 + 추천 결과 표시
- 실시간 광고 팝업 오버레이 (TV 화면 위)
- 홈쇼핑 채널 이동 / 시청예약 UX

**예정 폴더 구조:**
```
Frontend/
├── src/
│   ├── components/    ← VideoPlayer, AdPopup, RecommendList
│   ├── pages/         ← index, vod/[id], schedule
│   └── services/      ← api.ts (API_Server 클라이언트)
├── public/
└── tests/
```

---

## 개발 순서 요약

```
Phase 1 (현재)          Phase 2             Phase 3             Phase 4
─────────────────       ─────────────────   ─────────────────   ─────────────────
Database_Design   →     CF_Engine       →   Object_Detection →  API_Server
RAG               →     Vector_Search   →   Shopping_Ad      →  Frontend
VOD_Embedding
Poster_Collection
```

---

## 브랜치 생성 명령어 참고

```bash
# Phase 1 (추가)
git checkout main && git checkout -b Poster_Collection

# Phase 2
git checkout main && git checkout -b CF_Engine
git checkout main && git checkout -b Vector_Search

# Phase 3
git checkout main && git checkout -b Object_Detection
git checkout main && git checkout -b Shopping_Ad

# Phase 4
git checkout main && git checkout -b API_Server
git checkout main && git checkout -b Frontend
```
