# 프로젝트 전체 구조 및 설계 흐름 리포트

- **작성일**: 2026-03-19
- **작성 목적**: 전체 팀 설계 흐름 파악 및 타 모듈과의 연관관계 이해

---

## 프로젝트 목표

IPTV/케이블 VOD 콘텐츠를 분석하여 → 개인화 추천하고 → 재생 중 광고도 띄우는 풀스택 시스템 구현

---

## 데이터 흐름 전체 구조

```
원본 데이터 (VOD 166,159건 / 유저 242,702명)
        │
        ▼
┌──────────────────────────────────────────┐
│           Phase 1: 데이터 인프라          │
│                                          │
│  RAG ──────────────────────────────────→ vod.director/cast/smry 채움
│  Poster_Collection ────────────────────→ vod.poster_url 채움
│  VOD_Embedding ────────────────────────→ vod_embedding(512) + vod_meta_embedding(384)
│  User_Embedding ───────────────────────→ user_embedding(896) = VOD벡터 가중평균
│  Database_Design ──────────────────────→ 전체 PostgreSQL 스키마 관리
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│           Phase 2: 추천 엔진              │
│                                          │
│  CF_Engine ────────────────────────────→ serving.vod_recommendation (COLLABORATIVE)
│  Vector_Search ────────────────────────→ serving.vod_recommendation (VISUAL_SIMILARITY)
│  Hybrid_Layer ─────────────────────────→ serving.hybrid_recommendation (리랭킹 + 설명)
└──────────────────────────────────────────┘
        │
        ├──────────────────────────────────┐
        ▼                                  ▼
┌──────────────────┐            ┌──────────────────────────┐
│  Phase 3: 영상AI  │            │    Phase 4: 서비스        │
│                  │            │                          │
│  Object_Detection│            │  API_Server (FastAPI)    │
│  → parquet 로컬  │            │  → 추천/광고 엔드포인트   │
│                  │            │                          │
│  Shopping_Ad     │            │  Frontend (React/Next.js)│
│  → 팝업 트리거   │            │  → UI + 광고 팝업        │
└──────────────────┘            └──────────────────────────┘
```

---

## 모듈별 역할 상세

### Database_Design
스키마 단일 진실 원천(SSoT). 모든 팀원이 여기 SQL 파일 보고 테이블 구조 확인.
- `schemas/` — 테이블 DDL (CREATE TABLE)
- `migrations/` — 스키마 변경 이력
- `docs/DEPENDENCY_MAP.md` — 누가 어느 테이블을 읽고 쓰는지 전체 지도

---

### RAG
VOD 메타데이터 결측치 자동수집. 감독명/배우/줄거리가 비어있는 166,159건을
TMDB → KMDB → JustWatch → Naver 순서로 채움.

| 컬럼 | 완성률 |
|------|--------|
| director | 92.5% |
| cast_lead | 72.0% |
| release_date | 74.9% |
| rating | 65.6% |
| cast_guest | 53.0% |

---

### Poster_Collection
VOD 포스터 이미지 URL 수집. Naver에서 시리즈명으로 검색 → `vod.poster_url` 적재.

---

### VOD_Embedding
VOD를 두 가지 벡터로 변환.
- **CLIP (512차원)**: YouTube 트레일러 프레임 → 영상 내용 벡터 → `vod_embedding`
- **메타 (384차원)**: 제목+장르+감독+출연+줄거리 → 텍스트 벡터 → `vod_meta_embedding`
- 팀원 4명이 장르별 분담 병렬 작업 중

---

### User_Embedding
유저 시청 이력 기반 유저 벡터 생성.

```
watch_history × (vod_embedding 512 + vod_meta_embedding 384)
    → 시청 완주율 가중 평균
    → user_embedding (896차원) 적재
```

CF_Engine과 Vector_Search가 이 벡터를 입력으로 사용 — **User_Embedding 완료 전 추천 엔진 실행 불가**.

---

### CF_Engine (본 브랜치)
ALS(교대 최소 제곱) 행렬 분해 기반 협업 필터링 추천 엔진.

**입력**
- `public.watch_history` — 유저×VOD 시청 행렬
- `public.user_embedding` — ALS 초기값

**출력**
- `serving.vod_recommendation` (`recommendation_type = 'COLLABORATIVE'`)

**주요 구현 사항**
- 하이퍼파라미터 튜닝 완료 (factors=128, iterations=20, regularization=0.01, alpha=40)
- cold VOD 필터링 (poster_url 또는 vod_embedding 없는 27.9% 제외)
- content_boost: 동일 감독/배우 3편 이상 시청 유저에게 태그 기반 가중치 추가
- top_k=10 (현재 설정)

**Hybrid_Layer와의 관계**: CF 결과(top-10)를 Hybrid_Layer가 읽어서 Vector_Search 결과와 합쳐 리랭킹.
> ⚠️ Hybrid_Layer 설계 기준은 CF top-20. top_k 조정 필요 여부 팀장과 협의 필요.

---

### Vector_Search
벡터 유사도 검색으로 추천.
- **유저 기반**: `user_embedding(896)` ↔ `vod_embedding(512+384)` 코사인 유사도 → `VISUAL_SIMILARITY`
- **콘텐츠 기반**: VOD ↔ VOD 유사도 → `CONTENT_BASED`
- 결과 → `serving.vod_recommendation` 적재

---

### Hybrid_Layer (설계 완료, 구현 예정)
CF + Vector 결과를 합쳐 리랭킹 후 추천 근거까지 생성.

```
CF top-20 + Vector top-20
    → 중복 제거 (최대 40 → 유니크 후보)
    → vod_tag × user_preference 태그 매칭
    → hybrid_score = 0.6 × 원점수 + 0.4 × 태그 매칭도
    → serving.hybrid_recommendation 적재
    → explanation_tags: "봉준호 감독 작품을 즐겨 보셨어요"
```

신규 테이블: `vod_tag`, `user_preference`, `serving.hybrid_recommendation`, `serving.tag_recommendation`

---

### Object_Detection
VOD 영상에서 사물/개념/음성 추출 (로컬 배치 처리, VPC 미적재).

| 모델 | 출력 파일 | 내용 |
|------|-----------|------|
| YOLOv8 | `vod_detected_object.parquet` | 프레임별 사물 탐지 (bbox, label) |
| CLIP | `vod_clip_concept.parquet` | 개념 태깅 (음식/여행/상품 등) |
| Whisper STT | `vod_stt_concept.parquet` | 음성 → 텍스트 → 광고 키워드 |

→ 로컬 parquet 3종을 Shopping_Ad에서 소비.

---

### Shopping_Ad
VOD 재생 중 홈쇼핑 팝업 광고 시스템.

```
① 배치 사전 계산
   Object_Detection parquet 3종 소비
   + 세부장르(먹방/여행/토크쇼) 기반 트리거 조건 적용
   → trigger_points.parquet (vod_id, time_sec, ad_category)

② 매일 자정
   홈쇼핑 tv_schedule 수집 → 광고 매칭 업데이트
   → serving.shopping_ad 적재

③ 실시간 발화
   시청자 VOD 재생 중 time_sec 도달
   → API_Server가 팝업 발화
```

팝업 예시:
```json
{
  "trigger_label": "음식",
  "product_name": "영광 굴비 선물세트",
  "channel": "GS샵",
  "price": "59,000원",
  "actions": ["채널이동", "시청예약"]
}
```

---

### API_Server
FastAPI 백엔드. DB에서 추천/광고 데이터 읽어서 프론트에 전달.

| 엔드포인트 | 소스 테이블 |
|-----------|------------|
| `GET /recommend/{user_id}` | `serving.hybrid_recommendation` |
| `GET /similar/{asset_id}` | `serving.vod_recommendation` (CONTENT_BASED) |
| `WS /ad/popup` | `serving.shopping_ad` |

---

### Frontend
React/Next.js UI. 추천 목록 표시 + VOD 재생 중 광고 팝업 오버레이.
- VideoPlayer, RecommendList, AdPopup 컴포넌트
- 홈쇼핑 채널이동 / 시청예약 UX

---

## 현재 진행 상황

| 모듈 | 상태 |
|------|------|
| Database_Design | ✅ 스키마 완성, 지속 업데이트 중 |
| RAG | ✅ 메타데이터 수집 완료 (90%+) |
| Poster_Collection | ✅ 완료 |
| VOD_Embedding | 🔄 진행 중 (팀원 분담 병렬 작업) |
| User_Embedding | 🔄 진행 중 |
| CF_Engine | 🔄 구현 완료, 평가 및 튜닝 중 |
| Vector_Search | 📋 설계 완료, 구현 예정 |
| Hybrid_Layer | 📋 설계 완료 (DDL 완성), 구현 예정 |
| Object_Detection | 🔄 진행 중 |
| Shopping_Ad | 🔄 진행 중 (전략: 홈쇼핑→제철장터/지자체 광고로 전환) |
| API_Server | 📋 설계 중 |
| Frontend | 📋 미시작 |

---

## DB 테이블 의존 관계 요약 (CF_Engine 관점)

### 업스트림 (내가 읽는 것)
| 테이블 | 생산자 | 용도 |
|--------|--------|------|
| `public.watch_history` | 초기 적재 | 행렬 분해 입력 |
| `public.user_embedding` | User_Embedding | ALS 초기값 |

### 다운스트림 (내가 쓰는 것 → 읽어가는 곳)
| 테이블 | 소비자 |
|--------|--------|
| `serving.vod_recommendation` (COLLABORATIVE) | Hybrid_Layer, API_Server |
| `serving.popular_recommendation` (POPULAR) | API_Server |
