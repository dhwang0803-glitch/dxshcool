# VOD Recommendation — 전체 개발 로드맵

> 최종 목표: IPTV/케이블 VOD 콘텐츠 지능형 추천·광고 시스템 풀스택 구현

---

## 시스템 아키텍처 개요

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend                             │
│          Next.js + Tailwind CSS + TypeScript — 시청자 UI + 광고 팝업              │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST / WebSocket
┌──────────────────────────▼──────────────────────────────────┐
│                       API_Server                            │
│         FastAPI — 추천 / 검색 / 광고 엔드포인트             │
└────┬──────────────┬──────────────┬──────────────────────────┘
     │              │              │
     ▼              ▼              ▼
┌──────────────────────────────────┐  ┌───────────────────────┐
│          Hybrid_Layer            │  │     Shopping_Ad        │
│  리랭킹 + 설명 가능한 추천       │  │  지자체 광고+제철장터  │
│  (vod_tag × user_preference)     │  ├───────────────────────┤
├────────────────┬─────────────────┤  │   Object_Detection    │
│   CF_Engine    │  Vector_Search  │  │  YOLO+CLIP+STT+OCR   │
│   행렬분해     │  ┌───────────┐  │  │  영상 인식 → 광고    │
│   추천엔진     │  │콘텐츠 기반│  │  │  트리거 추출         │
│   (ALS)       │  │유사도검색  │  │  └───────────┬─────────┘
│               │  ├───────────┤  │              │
│               │  │시각적 유사 │  │              │
│               │  │도 기반추천 │  │              │
│               │  └───────────┘  │              │
└───────┬────────┴────────┬───────┘              │
        │                 │                      │
        └─────────────────┼──────────────────────┘
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

### 추천 엔진 계층 구조

```
┌─────────────────────────────────────────────────────┐
│                   Hybrid_Layer                       │
│        리랭킹 + 설명 가능한 추천 (최종 출력)         │
│   CF + Vector 후보 통합 → tag 기반 리랭킹 → top 10  │
├────────────────────────┬────────────────────────────┤
│      CF_Engine         │       Vector_Search        │
│   협업 필터링 (ALS)    │  ┌──────────────────────┐  │
│   User-Item 행렬분해   │  │  콘텐츠 기반 추천    │  │
│   → COLLABORATIVE     │  │  메타(384)+영상(512) │  │
│                        │  │  앙상블 → item-to-   │  │
│                        │  │  item 유사 콘텐츠    │  │
│                        │  │  → CONTENT_BASED     │  │
│                        │  ├──────────────────────┤  │
│                        │  │  시각적 유사도 추천  │  │
│                        │  │  user CLIP[:512] ×   │  │
│                        │  │  VOD CLIP 벡터       │  │
│                        │  │  → user-to-item      │  │
│                        │  │  → VISUAL_SIMILARITY │  │
│                        │  └──────────────────────┘  │
└────────────────────────┴────────────────────────────┘
```

---

### `CF_Engine` — 협업 필터링 (행렬 분해) `구현 완료`
- 시청 이력 기반 User-Item 행렬 구성
- ALS (Alternating Least Squares) 적용
- 추천 결과는 `serving.vod_recommendation` 테이블에 사전 적재 → API 서버에서 PK 조회 (인프라 제약으로 Redis 미도입)
- 추천 유형: `COLLABORATIVE`

**폴더 구조:**
```
CF_Engine/
├── src/           ← als_model.py, data_loader.py, recommender.py, base.py
├── scripts/       ← train.py
├── tests/
└── config/
```

---

### `Vector_Search` — 벡터 유사도 검색 (2종) `구현 완료`

#### 1) 콘텐츠 기반 추천 (CONTENT_BASED) — item-to-item
- **메타데이터 기반**: `vod_series_embedding`(384차원) 코사인 유사도 (pgvector `<=>`)
- **영상 기반**: `vod_embedding`(512차원) 코사인 유사도 (pgvector `<=>`)
- 위 두 스코어 앙상블 → `CONTENT_BASED` item-to-item 유사 콘텐츠 순위 (source_vod_id → similar VODs)

#### 2) 시각적 유사도 추천 (VISUAL_SIMILARITY) — user-to-item
- `user_embedding` CLIP 부분([:512]) × VOD CLIP 벡터 → 유저가 시각적으로 선호하는 VOD 추천
- 멀티프로세스 병렬 + COPY 벌크 적재

**폴더 구조:**
```
Vector_Search/
├── src/
│   ├── base.py                ← VectorSearchBase 공통 베이스
│   ├── content_based.py       ← 메타데이터 기반 유사도
│   ├── clip_based.py          ← 영상 임베딩 기반 유사도
│   ├── ensemble.py            ← 앙상블 로직
│   └── visual_similarity.py   ← 유저 CLIP 기반 시각 유사도
├── scripts/
│   ├── run_pipeline.py            ← CONTENT_BASED 배치 파이프라인
│   └── run_visual_similarity.py   ← VISUAL_SIMILARITY 배치 파이프라인
├── tests/
└── config/
```

---

### `Hybrid_Layer` — 설명 가능한 추천 (Explainable Recommendation) `구현 완료`
- CF_Engine(COLLABORATIVE) + Vector_Search(CONTENT_BASED, VISUAL_SIMILARITY)의 추천 후보를 입력으로 수신
- `vod_tag`(감독/배우/장르) × `user_preference`(유저 선호 프로필) 매칭
- 중복 제거 + 태그 기반 리랭킹 → 최종 top 10 + `explanation_tags` 생성
- `serving.hybrid_recommendation`에 적재 → 홈 배너 3단 구조의 3단 영역
- `serving.tag_recommendation`에 적재 → `/recommend` 패턴 그룹핑 서빙

**홈 배너 3단 구조:**
```
1단: Normal_Recommendation → personalized_banner (유저별 top 5)
2단: Normal_Recommendation → popular_recommendation (비개인화 top 5)
3단: Hybrid_Layer → hybrid_recommendation (top 10)
```

**Hybrid_Layer 입력 소스:**
```
CF_Engine ──── COLLABORATIVE (행렬분해 기반) ──────────┐
                                                       ├→ Hybrid_Layer → 리랭킹 → top 10
Vector_Search ─┬ CONTENT_BASED (콘텐츠 유사도) ────────┤
               └ VISUAL_SIMILARITY (시각 유사도) ──────┘
```

**설명 가능한 추천 예시:**
```
"봉준호 감독 작품을 즐겨 보셨어요" (director affinity 0.92)
"송강호 배우 출연작을 자주 시청하셨네요" (actor affinity 0.85)
```

**폴더 구조:**
```
Hybrid_Layer/
├── src/
│   ├── base.py               ← 공통 베이스
│   ├── tag_builder.py        ← Phase 1: vod → vod_tag 태그 추출
│   ├── preference_builder.py ← Phase 2: watch_history × vod_tag → user_preference
│   ├── reranker.py           ← Phase 3: 후보 리랭킹 + explanation 생성
│   └── shelf_builder.py      ← Phase 4: 선호 태그별 VOD 선반 생성
├── scripts/
│   ├── build_vod_tags.py         ← Phase 1 실행
│   ├── build_user_preferences.py ← Phase 2 실행
│   ├── run_hybrid.py             ← Phase 3 리랭킹 + 적재
│   └── build_tag_shelves.py      ← Phase 4 선반 생성
├── tests/
│   ├── test_tag_builder.py       ← 15 tests
│   └── test_reranker.py          ← 3 tests
└── config/
    └── hybrid_config.yaml        ← β=0.6, top_n=10 등
```

> **데이터 현황 (2026-03-22)**: COLLABORATIVE 4,854,040건 + CONTENT_BASED 2,394,600건 적재 완료.
> Phase 1(vod_tag 1,331,164건) 완료. Phase 2(user_preference) 실행 중 → Phase 3~4 대기.
> 상세 현황: `docs/DATA_PIPELINE_STATUS.md`

---

## Phase 3 — 영상 AI 광고 시스템

> **인프라 제약**: VPC 1 core / 1GB RAM (+3GB swap) / 150GB Storage
> → 모든 연산은 **로컬**에서 수행, VPC는 `serving.*` 테이블만 제공하는 **thin serving layer**

### `Shopping_Ad` — 지자체 광고 팝업 + 제철장터 채널 연계

> **2026-03-19 방향 전환**: 홈쇼핑 연동 폐기 → 지자체 광고 + 제철장터 연계로 전환.

**핵심 아이디어**: VOD 영상을 4종 AI 모델로 분석하여,
관광지/지역 인식 시 지자체 광고 팝업을, 음식 인식 시 제철장터 채널 연계를 트리거한다.

| 인식 대상 | 광고 액션 | 예시 |
|----------|---------|------|
| 관광지/지역 (진주, 여수 등) | 지자체 광고 팝업 (생성형 AI 제작, OCI 저장) | 진주 동물축제 광고 |
| 음식 (삼겹살, 한우 등) | 제철장터 채널 상품 연계 (채널 이동/시청예약) | 한우 축제, 김치 축제 |

#### Object_Detection (하위 모듈) — VOD 배치 사물인식

Shopping_Ad의 입력 데이터를 생성하는 영상 인식 파이프라인.

| 모델 | 인식 대상 | 출력 |
|------|----------|------|
| YOLOv11s (한식 71종 커스텀) | 시각 객체 (음식, 사물) | `vod_detected_object.parquet` |
| CLIP (ViT-B/32) | 추상적 개념 (벚꽃 풍경, 전통시장) | `vod_clip_concept.parquet` |
| Whisper (STT) | 음성 키워드 (지역명, 음식명) | `vod_stt_concept.parquet` |
| EasyOCR | 화면 텍스트 (자막, 간판) | `vod_ocr_concept.parquet` |

**처리 흐름 (3단계):**

```
━━━ ① Object_Detection: 영상 인식 (로컬 배치) ━━━━━━━━━━━━━

VOD 영상 파일
    → 프레임 추출 (N fps 샘플링)
    → 4종 모델 배치 추론 (YOLO + CLIP + Whisper + EasyOCR)
    → 4종 parquet 산출물 생성

━━━ ② Shopping_Ad: 광고 매칭 + 소재 생성 ━━━━━━━━━━━━━━━━━

4종 parquet 소비 → 인식 대상별 트리거 조건 적용:
  관광지/지역 → STT 지역명 + CLIP 지역 개념 → 지자체 광고 팝업
  음식        → YOLO 음식 bbox + CLIP 음식 개념 → 제철장터 채널 연계

축제 리스트 수집 → 생성형 AI 팝업 이미지 제작 → OCI 업로드
→ serving.shopping_ad 적재

━━━ ③ 실시간 팝업 발화 (API_Server) ━━━━━━━━━━━━━━━━━━━━━━

시청자 VOD 재생 시작
→ API_Server: serving.shopping_ad WHERE vod_id=$1 조회
→ 재생 중 time_sec 도달
→ 관광지/지역: 지자체 광고 팝업 표시
→ 음식: 제철장터 채널 이동/시청예약 안내
```

**테이블 소유:**

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `detected_object_yolo` | **VPC** | YOLO 객체 탐지 결과 |
| `detected_object_clip` | **VPC** | CLIP 개념 태깅 결과 |
| `detected_object_stt` | **VPC** | Whisper STT 키워드 |
| `detected_object_ocr` | **VPC** | EasyOCR 텍스트 추출 |
| `seasonal_market` | **VPC** | 제철장터 편성표 |
| `serving.shopping_ad` | **VPC** | 트리거 포인트 + 광고 액션 (API_Server 직접 조회) |

**의존 관계:**
- `Database_Design` — `serving.shopping_ad`, `detected_object_*` 스키마
- `API_Server` — `/ad/popup` trigger_ts 기반 발화 엔드포인트

**폴더 구조:**
```
Object_Detection/                    Shopping_Ad/
├── src/                             ├── src/
│   ├── detector.py                  │   ├── trigger_extractor.py
│   ├── frame_extractor.py           │   ├── product_mapper.py
│   ├── clip_tagger.py               │   ├── epg_parser.py
│   ├── stt_extractor.py             │   ├── popup_builder.py
│   └── ocr_extractor.py             │   └── serving_writer.py
├── scripts/                         ├── scripts/
│   └── batch_detect.py              │   ├── run_ad_matching.py
├── tests/                           │   └── ingest_to_db.py
├── config/                          ├── tests/
└── docs/                            ├── config/
                                     └── docs/
```

---

## Phase 4 — 서비스 레이어

### `API_Server` — FastAPI 백엔드
- 추천 엔드포인트: `/recommend/{user_id}`, `/similar/{asset_id}`
- 광고 트리거: `/ad/popup` (WebSocket)
- 인증: JWT (셋톱박스 자동 로그인, 만료 없음)
- **실시간 처리 (방안 A — Redis 미도입)**: 인프라 제약(1GB RAM)으로 Redis 대신 PG 내장 기능 + 인메모리 버퍼 채택
  - 시청 진행률: 인메모리 버퍼 → 60초 batch UPSERT
  - 마이페이지 실시간 갱신: PG LISTEN/NOTIFY → WebSocket push
  - 포인트 잔액: DB 트리거 자동 갱신 (point_history INSERT → user.point_balance UPDATE)
  - 시청예약 알림: 30초 주기 background task → WebSocket push

**폴더 구조:**
```
API_Server/
├── app/
│   ├── routers/       ← auth, home, vod, series, user, purchase, wishlist, recommend, similar, ad, reservation
│   ├── services/      ← 비즈니스 로직, progress_buffer, pg_listener, reservation_checker, exceptions
│   ├── models/        ← Pydantic 요청/응답 스키마
│   └── main.py
├── tests/
├── config/
└── docs/              ← realtime_architecture.md, error_message_policy.md
```

---

### `Frontend` — Next.js + Tailwind CSS + TypeScript 클라이언트
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
Phase 1                 Phase 2                      Phase 3             Phase 4
─────────────────       ───────────────────────────  ─────────────────   ─────────────
Database_Design   →     CF_Engine (COLLABORATIVE) ─┐                    API_Server
RAG               →     Vector_Search             │→ Hybrid_Layer →   Frontend
VOD_Embedding(512+384)↘  ├ CONTENT_BASED          │
User_Embedding(896) ──→   └ VISUAL_SIMILARITY ────┘
Poster_Collection                                    Shopping_Ad
                                                      └ Object_Detection
```

> **의존 관계**:
> - `vod_embedding`(512) + `vod_meta_embedding`(384) 모두 적재 완료 후 User_Embedding 학습 가능
> - CF_Engine / Vector_Search 실행 전 `user_embedding`(896) 적재 완료 필요
> - Hybrid_Layer는 CF_Engine + Vector_Search 양쪽의 추천 결과를 입력으로 받아 최종 리랭킹 수행

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
