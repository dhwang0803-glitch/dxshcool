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
│행렬분해  │  │Search      │  │지자체 광고   │
│추천엔진  │  │유사도검색  │  │+제철장터    │
└────┬────┘  └─────┬──────┘  └──────┬───────┘
     │              │                │
     └──────────────┼────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│          VPC PostgreSQL + pgvector (thin serving layer)      │
│  1 core / 1GB RAM (+3GB swap) / 150GB Storage               │
│  vod / vod_embedding(512) / vod_meta_embedding(384)         │
│  user_embedding(896) / serving.shopping_ad                  │
└───────────┬──────────────────────────────────────────────────┘
            │ 데이터 공급 (로컬 → VPC 적재)
┌───────────▼──────────────────────────────────────────────────┐
│              데이터 파이프라인 (로컬 연산)                    │
│   RAG (메타데이터)  ·  VOD_Embedding (CLIP 512 + 메타 384)  │
│   User_Embedding (ALS 행렬분해, 896차원)                     │
│   Poster_Collection (포스터)                                 │
│   Object_Detection (YOLO 배치 → parquet, 로컬 전용)         │
│   Shopping_Ad (매칭 엔진 → serving.shopping_ad VPC 적재)     │
└──────────────────────────────────────────────────────────────┘
```

---

## Phase 1 — 데이터 인프라 `진행 중`

### `Database_Design`
- PostgreSQL 스키마 설계 (vod, vod_embedding, user_embedding, vod_recommendation 등)
- pgvector 확장 설정 — **벡터 저장소 pgvector 단일화 결정 (2026-03-08)**. Milvus 미사용 (인프라 복잡도 사유)
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
- YouTube 트레일러 수집 (yt-dlp) → CLIP ViT-B/32 영상 임베딩 → **512차원** → `vod_embedding` 적재
- VOD 메타데이터 (제목/장르/감독/출연/줄거리) → paraphrase-multilingual-MiniLM-L12-v2 → **384차원** → `vod_meta_embedding` 적재
- 두 벡터를 concat하면 **896차원 VOD 결합 벡터** → `User_Embedding` 학습 입력으로 사용

**팀 분할 (4명 병렬 작업):**
| 팀원 | 담당 | 건수 |
|------|------|-----:|
| A | TV 연예/오락 앞 절반 | ~9,570 |
| B | TV 연예/오락 뒤 절반 | ~9,571 |
| C | 영화 + TV드라마 + 키즈 | ~11,508 |
| D | TV애니메이션 + TV 시사/교양 + 기타 등 | ~11,102 |

**현황 (파일럿 100건):**
- 영상 임베딩: 크롤링 98%, 임베딩 78%, DB 적재 완료
- 메타데이터 임베딩: `src/meta_embedder.py` 구현 완료, 전체 실행 예정

**폴더 구조:**
```
VOD_Embedding/
├── src/           ← meta_embedder.py, embedder.py(예정), db.py, config.py
├── scripts/       ← crawl_trailers, batch_embed, ingest_to_db, split_tasks
├── tests/
├── config/
└── docs/
```

---

### `User_Embedding`
- `vod_embedding`(512차원) + `vod_meta_embedding`(384차원)을 L2 정규화 후 concat → **896차원 VOD 결합 벡터** 구성
- ALS(Alternating Least Squares) 행렬 분해로 동일 896차원 잠재 공간에서 **User 임베딩** 학습
- 출력: `user_embedding` 테이블 (`VECTOR(896)`) → pgvector 적재
- CF_Engine 및 Vector_Search에서 개인화 추천 입력으로 사용

> ⚠️ **차원 축소 미확정**: 896차원 연산 부담 시 PCA/Autoencoder로 축소 예정.
> 원본 VOD 임베딩(512, 384)은 별도 테이블에 보존되므로 재학습 시 차원 변경 가능.

**사전 조건:**
- `VOD_Embedding` — `vod_embedding`(512), `vod_meta_embedding`(384) 적재 완료
- `Database_Design` — `user_embedding VECTOR(896)` 테이블 생성 완료

**워크플로우:**
```
vod_embedding(512) + vod_meta_embedding(384)
    → 각각 L2 정규화 → concat → VOD 결합 벡터 [896차원]

watch_history (user_id, asset_id, completion_rate)
    → User-Item 희소 행렬 구성
    → ALS 학습 (item latent factor 초기값 = VOD 결합 벡터 [896차원])
    → User 잠재 벡터 [896차원] 산출
    → user_embedding 테이블 upsert
```

**예정 폴더 구조:**
```
User_Embedding/
├── src/           ← mf_model.py, vod_embedding_loader.py, data_loader.py
├── scripts/       ← train.py, export_to_db.py
├── tests/
└── config/        ← mf_config.yaml (factors: 896, iterations: 20)
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
- **메타데이터 기반**: `vod_meta_embedding`(384차원) 코사인 유사도 (pgvector `<=>`)
- **영상 기반**: `vod_embedding`(512차원) 코사인 유사도 (pgvector `<=>`)
- 두 스코어 앙상블 → 최종 유사도 순위
- User 임베딩(`user_embedding` 896차원) 활용 시 개인화 검색 가능

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

> **인프라 제약**: VPC 1 core / 1GB RAM (+3GB swap) / 150GB Storage
> → 모든 연산은 **로컬**에서 수행, VPC는 `serving.*` 테이블만 제공하는 **thin serving layer**

### `Object_Detection` — VOD 배치 사물인식
- 모델: YOLOv8n (속도 우선) / YOLOv8x (정확도 우선)
- 방식: **배치 사전 분석** (실시간 아님) — VOD 프레임을 로컬에서 일괄 추론
- 입력: VOD 영상 파일 프레임 (N fps 샘플링)
- 출력: `vod_detected_object.parquet` (로컬 저장, VPC 미적재)
- 산출물: `(vod_id, frame_ts, label, confidence, bbox)` — Shopping_Ad에서 소비

**테이블 소유:**

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `vod_detected_object` | 로컬 parquet | VOD별 감지 객체 (label, confidence, bbox, frame_ts) |

**데이터 플로우:**
```
VOD 영상 파일
    → 프레임 추출 (N fps 샘플링)
    → YOLOv8 배치 추론 (로컬 GPU/CPU)
    → 신뢰도 필터링 (>= 0.5)
    → vod_detected_object.parquet 저장 (로컬)
    → Shopping_Ad가 parquet 소비
```

**예정 폴더 구조:**
```
Object_Detection/
├── src/           ← detector.py, frame_extractor.py
├── scripts/       ← batch_detect.py (배치 사전 분석)
├── tests/
├── config/        ← detection_config.yaml (모델, 임계값, fps)
└── docs/
```

---

### `Shopping_Ad` — 지자체 광고 팝업 + 제철장터 채널 연계

> **2026-03-19 방향 전환**: 홈쇼핑 연동 폐기 → 지자체 광고 + 제철장터 연계로 전환.

**핵심 아이디어**: Object_Detection의 장면 인식 결과를 기반으로,
관광지/지역 인식 시 지자체 광고 팝업을, 음식 인식 시 제철장터 채널 연계를 트리거한다.

| 인식 대상 | 광고 액션 | 예시 |
|----------|---------|------|
| 관광지/지역 (진주, 여수 등) | 지자체 광고 팝업 (생성형 AI 제작, OCI 저장) | 진주 동물축제 광고 |
| 음식 (삼겹살, 한우 등) | 제철장터 채널 상품 연계 (채널 이동/시청예약) | 한우 축제, 김치 축제 |

**처리 흐름 (3단계):**

```
━━━ ① 배치 처리 (사전 계산) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Object_Detection 3종 parquet 소비:
  vod_detected_object.parquet  ← YOLO bbox
  vod_clip_concept.parquet     ← CLIP 개념 태깅
  vod_stt_concept.parquet      ← Whisper STT 키워드

인식 대상별 트리거 조건 적용:
  관광지/지역 → STT 지역명 + CLIP 지역 개념 → 지자체 광고 팝업
  음식        → YOLO 음식 bbox + CLIP 음식 개념 → 제철장터 채널 연계

→ trigger_points.parquet (vod_id, time_sec, ad_category, ad_action_type)

━━━ ② 광고 소재 생성 (MVP: 수동/반자동) ━━━━━━━━━━━━━━━━━━━

축제 리스트 수집 (예: 3~4월 지역 축제)
→ 생성형 AI로 팝업 광고 이미지 제작
→ OCI Object Storage 업로드
→ serving 테이블에 광고 이미지 URL 적재

━━━ ③ 실시간 팝업 발화 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

시청자 VOD 재생 시작
→ API_Server: serving.shopping_ad WHERE vod_id=$1 조회
→ 재생 중 time_sec 도달
→ 관광지/지역: 지자체 광고 팝업 표시
→ 음식: 제철장터 채널 이동/시청예약 안내
```

**테이블 소유:**

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `product_object_mapping` | 로컬 yaml/CSV | 인식 결과 → 광고 카테고리 매핑 (비즈니스 로직) |
| `serving.shopping_ad` | **VPC** | 트리거 포인트 + 광고 액션 (API_Server 직접 조회) |

**의존 관계:**
- `Object_Detection` — 3종 parquet 생성 완료 후 트리거 추출 가능
- `Database_Design` — `serving.shopping_ad` 스키마 재설계 필요 (지자체 광고 + 제철장터 반영)
- `API_Server` — `/ad/popup` trigger_ts 기반 발화 엔드포인트 구현 (PLAN_06)

**예정 폴더 구조:**
```
Shopping_Ad/
├── src/           ← trigger_extractor.py, product_mapper.py, epg_parser.py
│                     popup_builder.py, serving_writer.py
├── scripts/       ← run_shopping_ad.py, run_epg_sync.py, ingest_to_db.py
├── tests/
├── config/        ← ad_config.yaml
└── docs/          ← plans/, reports/
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
- 지자체 광고 팝업 오버레이 + 제철장터 채널 이동/시청예약 UX

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
VOD_Embedding(512+384)↘
User_Embedding(896) ──→  CF_Engine / Vector_Search (user+item 벡터 입력)
Poster_Collection
```

> **의존 관계 (User_Embedding 선행 필요)**:
> - `vod_embedding`(512) + `vod_meta_embedding`(384) 모두 적재 완료 후 User_Embedding 학습 가능
> - CF_Engine / Vector_Search 실행 전 `user_embedding`(896) 적재 완료 필요

---

## 브랜치 생성 명령어 참고

```bash
# Phase 1 (추가)
git checkout main && git checkout -b User_Embedding
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
