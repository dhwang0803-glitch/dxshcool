# 홈/추천 배너 API 변경사항 — 프론트엔드 연동 가이드

> 최종 수정: 2026-03-31
> 대상: Frontend 팀 (홈 페이지 + 스마트 추천 페이지)

---

## Dev API Base URL

```
https://vod-api-dev-121620013082.asia-northeast3.run.app
```

## Prod API Base URL

```
https://vod-api-121620013082.asia-northeast3.run.app
```

> 개발 테스트는 `vod-api-dev`, 운영은 `vod-api`로 호출.

---

## 변경 요약

| 변경 항목 | 내용 |
|-----------|------|
| **top_vod 10건 배열** | 스마트 추천 히어로 영역이 단건 → **배열 10건**(backdrop_url 포함)으로 확장 |
| **Cold Start 배너 추가** | 시청 이력이 적은 유저에게 연령대 인기 장르 배너가 추가됨 (`cold_genre_detail`) |
| **홈 개인화 섹션 구조 확장** | 태그 배너 + 벡터 유사도 배너 + TOP10 배너 = 최대 ~10개 섹션 |
| **TOP10 배너에 추천 문구** | `rec_sentence` 필드 추가 (nullable, LLM 생성) |
| **view_ratio 선택적** | 벡터/TOP10 섹션에는 `view_ratio`가 없음 → `null` 허용 |
| **스마트 추천 cold 패턴** | 기존 genre_detail/director/actor 외에 `cold_genre_detail` 패턴 추가 |
| **backdrop_url 필수화** | top_vod, 히어로 배너에 backdrop_url IS NOT NULL 필터 적용 (OCI/TMDB 이미지) |

---

## 1. 홈 페이지 API

### 1-1. 히어로 배너 — `GET /home/banner`

**인증**: 선택적 (`Authorization: Bearer <token>` 있으면 개인화 2단 추가)

**응답 구조:**

```json
{
  "items": [
    {
      "series_nm": "시리즈명",
      "title": "에피소드명 (asset_nm)",
      "poster_url": "https://...",
      "category": "TV드라마",
      "score": 95.3
    }
  ],
  "total": 15
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `series_nm` | `string` | 시리즈명 (중복 제거 기준) |
| `title` | `string` | 개별 에피소드/자산명 |
| `poster_url` | `string \| null` | 포스터 이미지 URL (세로형) |
| `backdrop_url` | `string \| null` | 가로형 배경 이미지 URL (히어로 배너용, TMDB backdrop). **backdrop_url IS NOT NULL인 VOD만 응답에 포함** |
| `category` | `string \| null` | CT_CL (TV드라마, 영화, TV 연예/오락, 키즈) |
| `score` | `float \| null` | 인기 점수 |

**동작:**
- 비로그인: popular top 5
- 로그인: popular top 5 + hybrid top 10 (중복 제거, 최대 15개)

---

### 1-2. CT_CL 인기 섹션 — `GET /home/sections`

**인증**: 불필요

**응답 구조:**

```json
{
  "sections": [
    {
      "ct_cl": "TV드라마",
      "vod_list": [
        {
          "series_nm": "시리즈명",
          "title": "에피소드명",
          "poster_url": "https://...",
          "score": 88.5,
          "rank": 1
        }
      ]
    }
  ]
}
```

CT_CL 4종(TV드라마, 영화, TV 연예/오락, 키즈) × 인기순 VOD 목록. 비로그인/신규 유저 fallback용.

---

### 1-3. 개인화 섹션 — `GET /home/sections/{user_id}` ⭐ 변경

**인증**: 필수 (`Authorization: Bearer <token>`)

**응답 구조:**

```json
{
  "sections": [
    {
      "genre": "추천 인기 TV드라마",
      "view_ratio": 100,
      "vod_list": [
        {
          "series_nm": "시리즈명",
          "asset_nm": "에피소드명",
          "poster_url": "https://...",
          "score": null,
          "rank": null,
          "rec_reason": null,
          "rec_sentence": null
        }
      ]
    }
  ]
}
```

#### 필드 상세

| 필드 | 타입 | 설명 | nullable |
|------|------|------|----------|
| `genre` | `string` | 섹션 제목 (라벨) | N |
| `view_ratio` | `int \| null` | 시청 비중 (100~40). **벡터/TOP10 섹션에서는 `null`** | Y |
| `vod_list[].series_nm` | `string` | 시리즈명 | N |
| `vod_list[].asset_nm` | `string` | 에피소드/자산명 | N |
| `vod_list[].poster_url` | `string \| null` | 포스터 URL | Y |
| `vod_list[].score` | `float \| null` | 유사도/태그 점수. 벡터 섹션에서만 제공 | Y |
| `vod_list[].rank` | `int \| null` | TOP10 섹션에서만 제공 (1~10) | Y |
| `vod_list[].rec_reason` | `string \| null` | TOP10 추천 이유 (짧은 키워드) | Y |
| `vod_list[].rec_sentence` | `string \| null` | TOP10 추천 문구 (LLM 생성, 1~2문장) | Y |

#### 섹션 구성 (순서대로)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. 태그 배너: genre (시청 기반 인기 장르)                      │
│    genre: "추천 인기 {장르명}"                                │
│    view_ratio: 100 → 85 → 70 (감소)                         │
│    최대 3~5개 섹션                                            │
├─────────────────────────────────────────────────────────────┤
│ 2. Cold Start 배너: cold_genre_detail (연령대 인기) ⭐ 신규    │
│    genre: "{유저ID앞5자}님이 좋아할만한 {장르명} 시리즈"         │
│    view_ratio: (태그 배너 이어서 감소, 최소 40)                │
│    시청 이력 적은 유저에게만 노출 (빈 슬롯 채움)                 │
├─────────────────────────────────────────────────────────────┤
│ 3. 벡터 유사도 배너: 취향 기반 장르별 2그룹                     │
│    genre: "나의 취향과 비슷한 {장르명}"                        │
│    view_ratio: null (표시 불필요)                             │
│    최대 2개 섹션, 각 최대 10개 VOD                             │
├─────────────────────────────────────────────────────────────┤
│ 4. TOP10 배너: 태그 점수 상위 10개 ⭐ rec_sentence 포함        │
│    genre: "{유저ID앞5자}님만을 위한 추천 시리즈 TOP10"          │
│    view_ratio: null                                         │
│    rank: 1~10                                               │
│    rec_reason: "드라마 장르 선호" (nullable)                   │
│    rec_sentence: "가족의 비밀을 다룬 이 드라마는..." (nullable)  │
└─────────────────────────────────────────────────────────────┘
```

#### Fallback 동작

| 조건 | 결과 |
|------|------|
| 개인화 데이터 있음 | 위 4단 구조 반환 |
| 개인화 데이터 없음 (negative 유저 / 비로그인) | CT_CL 4종 fallback (`view_ratio: 0`) |

---

## 2. 스마트 추천 페이지 API

### 2-1. 개인화 추천 — `GET /recommend/{user_id}` ⭐ 변경

**인증**: 필수

**응답 구조:**

```json
{
  "user_id": "sha2_hash",
  "top_vod": [
    {
      "vod_id": "cjc|M1234...",
      "series_id": "시리즈명",
      "asset_nm": "에피소드명",
      "poster_url": "https://...",
      "backdrop_url": "https://...",
      "rec_sentence": "가족의 비밀을 파헤치는 이 드라마는..."
    }
  ],
  "patterns": [
    {
      "pattern_rank": 1,
      "pattern_reason": "TV드라마 장르를 즐겨 보셨어요",
      "vod_list": [
        {
          "series_id": "시리즈명",
          "asset_nm": "에피소드명",
          "poster_url": "https://...",
          "score": 0.85
        }
      ]
    }
  ],
  "source": "personalized"
}
```

#### 필드 상세

| 필드 | 타입 | 설명 |
|------|------|------|
| `top_vod` | `array` | 개인화 추천 top 10 VOD 배열 (히어로 캐러셀). hybrid 부족 시 cold_genre_detail로 보충 |
| `top_vod[].vod_id` | `string` | full_asset_id (PK) |
| `top_vod[].series_id` | `string` | series_nm 기준 시리즈명 |
| `top_vod[].asset_nm` | `string` | 자산명 |
| `top_vod[].poster_url` | `string` | 포스터 URL (세로형) |
| `top_vod[].backdrop_url` | `string` | 가로형 배경 이미지 URL (히어로 배너용). **IS NOT NULL 필터 적용** |
| `top_vod[].rec_sentence` | `string \| null` | LLM 생성 추천 문구 (세그먼트별 개인화, nullable) |
| `patterns[].pattern_rank` | `int` | 패턴 순서 (1부터) |
| `patterns[].pattern_reason` | `string` | 패턴 설명 라벨 (아래 참고) |
| `patterns[].vod_list[].series_id` | `string` | series_nm 기준 시리즈명 |
| `patterns[].vod_list[].asset_nm` | `string` | 자산명 |
| `patterns[].vod_list[].poster_url` | `string \| null` | 포스터 URL |
| `patterns[].vod_list[].score` | `float \| null` | 추천 점수 |
| `source` | `string` | `"personalized"` 또는 `"popular_fallback"` |

#### pattern_reason 라벨 종류

| 태그 카테고리 | pattern_reason 형식 | 예시 |
|--------------|---------------------|------|
| `genre_detail` | `{장르} 장르를 즐겨 보셨어요` | "TV드라마 장르를 즐겨 보셨어요" |
| `director` | `{감독명} 감독 작품을 즐겨 보셨어요` | "봉준호 감독 작품을 즐겨 보셨어요" |
| `actor_lead` | `{배우명} 배우 출연작을 자주 보셨어요` | "송강호 배우 출연작을 자주 보셨어요" |
| `actor_guest` | `{배우명} 배우가 출연한 프로그램을 모아봤어요` | "유재석 배우가 출연한 프로그램을 모아봤어요" |
| `cold_genre_detail` ⭐ 신규 | `{유저앞5자}님이 좋아할만한 {장르} 시리즈` | "f7328님이 좋아할만한 로맨스 시리즈" |
| 벡터 유사도 | `나의 취향과 비슷한 콘텐츠` | (고정 문구) |

#### 패턴 순서

```
1~N: 개인화 태그 패턴 (genre_detail → director → actor_lead → actor_guest)
N+1~: Cold Start 패턴 (cold_genre_detail) ⭐ 신규 — 시청 이력 적은 유저만
마지막: 벡터 유사도 패턴 ("나의 취향과 비슷한 콘텐츠")
```

#### Fallback 동작

| 조건 | `source` | 내용 |
|------|----------|------|
| 개인화 데이터 있음 | `"personalized"` | top_vod 10건 + 태그/cold/벡터 패턴 |
| 개인화 데이터 없음 | `"popular_fallback"` | top_vod = 인기 top 5, patterns = 인기 6~10위 |

> **프론트 분기 포인트**: `source` 값으로 개인화 vs fallback UI를 분기할 수 있음.

---

## 3. 프론트엔드 수정 체크리스트

### 홈 페이지 (`/home/sections/{user_id}`)

- [ ] `view_ratio`가 `null`인 섹션 처리 (벡터/TOP10 배너)
- [ ] `rec_reason`, `rec_sentence` 필드 렌더링 (TOP10 배너)
  - `rec_sentence`가 있으면 카드 하단에 추천 문구 표시
  - `null`이면 표시하지 않음
- [ ] `rank` 필드 렌더링 (TOP10 배너, 1~10 순위 뱃지)
- [ ] `score` 필드 — 벡터 섹션에서만 제공, 표시 여부는 디자인 판단
- [ ] Cold Start 배너 라벨 확인 ("`{5자}님이 좋아할만한 ... 시리즈`" 정상 출력)
- [ ] Fallback 시 `view_ratio: 0`인 CT_CL 4종 섹션 정상 렌더링

### 스마트 추천 페이지 (`/recommend/{user_id}`)

- [ ] `source === "popular_fallback"` 일 때 UI 분기 (예: "지금 인기 있는 콘텐츠" 헤더)
- [ ] Cold Start 패턴 라벨 정상 렌더링 ("`님이 좋아할만한 ... 시리즈`")
- [ ] 벡터 유사도 패턴 ("나의 취향과 비슷한 콘텐츠") 렌더링

---

## 4. 테스트 계정

> 상세 정보: `API_Server/docs/TESTER_ACCOUNTS.md` 참조

### Positive 테스터 (개인화 추천 있음) — 5명

| 레이블 | User ID (앞 8자) | 특징 |
|--------|-----------------|------|
| `C0_저관여_50대` | `f7328b31...` | Cold Start 배너 다수 노출 (시청 이력 적음) |
| `C1_충성_40대` | `877f7ce1...` | 태그 패턴 풍부, Shopping_Ad 연동 VOD 포함 |
| `C1_충성_60대` | `cf535eb5...` | 클래식·국악·다큐 선호 |
| `C2_헤비_50대` | `da3da6ae...` | 헤비 시청, 태그 패턴 최다 |
| `C3_키즈_40대` | `0486b86e...` | 키즈+성인 혼합 패턴 |

### Negative 테스터 (fallback 확인) — 7명

| 레이블 | User ID (앞 8자) |
|--------|-----------------|
| `C0_저관여_60대` | `077eec56...` |
| `C1_충성_50대` | `248cfc7f...` |
| `C1_충성_30대` | `b2bc8285...` |
| `C2_헤비_40대` | `121aaaa7...` |
| `C2_헤비_30대` | `a8bfccc8...` |
| `C3_키즈_30대` | `afcc0aa5...` |
| `C3_키즈_60대` | `1dcc3e37...` |

### 빠른 테스트 (curl)

```bash
# 개인화 있는 유저 — 홈 개인화 섹션
curl -H "Authorization: Bearer <TOKEN>" \
  "https://vod-api-dev-121620013082.asia-northeast3.run.app/home/sections/f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129"

# 개인화 있는 유저 — 스마트 추천
curl -H "Authorization: Bearer <TOKEN>" \
  "https://vod-api-dev-121620013082.asia-northeast3.run.app/recommend/f7328b318d191e3ef3ab456c7d7c8cc55ca85ff9f069ccd098f600a8e9561129"

# Fallback 유저 — 스마트 추천 (source: "popular_fallback" 확인)
curl -H "Authorization: Bearer <TOKEN>" \
  "https://vod-api-dev-121620013082.asia-northeast3.run.app/recommend/077eec56a021132c0ad3f7f94f1192d1821667258dfdcb00d9539a8f1bdfddc6"
```

> JWT 토큰은 `TESTER_ACCOUNTS.md` 참조 또는 `POST /auth/token`으로 발급.

---

## 5. 응답 예시 (실제 dev 서버 기준)

### 홈 개인화 섹션 — C0_저관여_50대 (Cold Start 포함)

```
섹션 수: 9개
├── genre 태그 3개     → "추천 인기 TV드라마", "추천 인기 로맨스", ...
│   view_ratio: 100, 85, 70
├── cold 태그 5개      → "f7328님이 좋아할만한 스릴러 시리즈", ...  ⭐
│   view_ratio: 55, 40, 40, 40, 40
├── 벡터 유사도 0~2개  → "나의 취향과 비슷한 TV드라마", ...
│   view_ratio: null
└── TOP10 1개         → "f7328님만을 위한 추천 시리즈 TOP10"
    view_ratio: null, rank: 1~10, rec_reason/rec_sentence 포함
```

### 스마트 추천 — C1_충성_40대 (개인화 풀)

```
source: "personalized"
top_vod: backdrop 있는 hybrid top 10건 (부족분 cold_genre_detail 보충)
         각 항목에 rec_sentence 포함 (세그먼트별 LLM 생성 문구)
patterns: 7개
├── actor_lead 2개    → "배우 출연작을 자주 보셨어요"
├── cold 태그 5개     → "877f7님이 좋아할만한 ... 시리즈"  ⭐
└── 벡터 유사도 1개   → "나의 취향과 비슷한 콘텐츠"
```

### 스마트 추천 — Negative 유저 (fallback)

```
source: "popular_fallback"
top_vod: 인기 top 5 VOD (backdrop 있는 것만)
patterns: 1개
└── "지금 인기 있는 콘텐츠" (인기 6~10위)
```
