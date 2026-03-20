# UI 시나리오 문서

> Figma 설계 기반. API Server 엔드포인트 설계 기준 문서.
> 작성일: 2026-03-19
> 참조: `skills/CLAUDE_API_Server.md`, `skills/CLAUDE_Hybrid_Layer.md`, `skills/ROADMAP.md`

---

## 페이지 목록

| 페이지 | 경로 | 설명 |
|--------|------|------|
| 홈 | `/` | 메인 홈 화면 |
| 스마트 추천 | `/recommend` | 유저 맞춤 추천 (Hybrid_Layer 결과) |
| 시리즈 상세 | `/series/:series_id` | 포스터 클릭 시 진입. VOD 시리즈 상세 + 에피소드 목록 |
| 마이 페이지 | `/my` | 사용자 시청/구매/찜 내역 |
| 구매 페이지 | `/purchase/:series_id` | VOD 구매 팝업/페이지 |

---

## 공통 컴포넌트

### GNB (Global Navigation Bar)
- 로고
- 네비게이션 탭: `홈` / `스마트 추천`
- 우측: 마이페이지 아이콘

> 시리즈 상세 페이지는 GNB에서 직접 진입하지 않는다. 홈/스마트 추천 어디서든 포스터 카드 클릭 시 해당 시리즈 상세 페이지로 이동한다.

### 포스터 카드 (PosterCard)
- 시리즈 포스터 이미지 (`poster_url`)
- 클릭 → 시리즈 상세 페이지 이동

### 가로 스크롤 섹션 (HorizontalSection)
- 섹션 타이틀
- 포스터 카드 가로 스크롤 (7개 노출, 이후 스크롤)
- 스크롤바 표시 (마지막 섹션)

### 광고 팝업 (AdPopup)
- `API_Server WebSocket /ad/popup` 구독
- VOD 재생 중 특정 시점(`time_sec`) 도달 시 오버레이 표시
- 광고 종류:
  - **지자체 광고**: 관광지/지역 인식 → 지자체 팝업 이미지 표시
  - **제철장터 연계**: 음식 인식 → 채널 이동 / 시청예약 버튼
- 버튼: `[채널 이동]` / `[시청 예약]` / `[닫기]`
- 닫기 or 액션 결과 → API_Server에 전송 (광고 효과 측정)

---

## 1. 홈 페이지 `/`

### 레이아웃 구성

```
[GNB]
[히어로 배너 - 캐러셀 top 5]
[섹션: 시청 중인 콘텐츠]      ← 가로 스크롤 (모바일카드형, 로그인 유저 전용)
[섹션: 인기 영화]             ← 가로 스크롤 (포스터형)
[섹션: 인기 드라마]           ← 가로 스크롤 (포스터형)
[섹션: 인기 예능]             ← 가로 스크롤 (포스터형)
[섹션: 인기 애니메이션]       ← 가로 스크롤 (포스터형)
[섹션: 개인화된 추천]         ← 가로 스크롤 (포스터형, Hybrid_Layer 결과, 로그인 유저 전용)
```

### UI 요소별 데이터

#### 히어로 배너 (캐러셀)
- 소스: `serving.hybrid_recommendation` (Hybrid_Layer 적재) top 20 중 `score` 내림차순 top 5
- 캐러셀 형태로 5개 순환 표시
- 로그인 유저 전용 (비로그인 시 Normal_Recommendation top 5로 대체)
- 필요 데이터: `poster_url`, `asset_nm`, `genre`, `disp_rtm`, `smry`, `score`
- 클릭 → `/series/:series_id` 이동 (버튼 없이 배너 전체가 클릭 영역)

#### 장르별 인기 섹션 (공통 구조)
- 소스: `serving.popular_recommendation` (Normal_Recommendation 적재, 매주 월요일 갱신)
- 고정 4개 CT_CL: `영화` / `TV드라마` / `TV 연예/오락` / `TV애니메이션` — 각 top 20

| 필드 | DB 컬럼 | 설명 |
|------|---------|------|
| `series_id` | `vod_id_fk` | 시리즈 식별자 |
| `asset_nm` | `vod.asset_nm` | 콘텐츠 제목 |
| `poster_url` | `vod.poster_url` | 포스터 이미지 URL |
| `ct_cl` | `serving.popular_recommendation.ct_cl` | 콘텐츠 분류 |
| `rank` | `serving.popular_recommendation.rank` | 인기 순위 |
| `score` | `serving.popular_recommendation.score` | 인기 점수 |

#### 시청 중인 콘텐츠 섹션
- 소스: `watch_history.strt_dt` 최신순 10개
- 포스터: `poster_url` 원본을 모바일 카드 크기로 크롭하여 표시 (원본 비율 유지 X, 카드 영역에 맞게 잘라냄)
- 로그인 유저 전용 (비로그인 시 미표시)

| 필드 | DB 컬럼 | 설명 |
|------|---------|------|
| `series_id` | `vod_id_fk` | 시리즈 식별자 |
| `asset_nm` | `vod.asset_nm` | 콘텐츠 제목 |
| `poster_url` | `vod.poster_url` | 포스터 (모바일 카드 크기로 크롭) |
| `strt_dt` | `watch_history.strt_dt` | 최근 시청일 (정렬 기준) |
| `completion_rate` | `watch_history.completion_rate` | 시청 진행률 (%) |

#### 개인화된 추천 섹션
- 소스: `serving.hybrid_recommendation` (Hybrid_Layer 적재)
- top 10 VOD 표시
- 로그인 유저 전용

### 필요 API

| 엔드포인트 | 설명 | 소스 |
|-----------|------|------|
| `GET /home/banner` | 히어로 배너 top 5 (Hybrid top 20 중 score 내림차순) | `serving.hybrid_recommendation` |
| `GET /home/sections` | 장르별 인기 섹션 전체 (CT_CL 4종 × top 20) | `serving.popular_recommendation` |
| `GET /user/{user_id}/watching` | 시청 중인 콘텐츠 (strt_dt 최신순 10개, completion_rate 포함) | DB (`watch_history`) |
| `GET /recommend/{user_id}` | 개인화된 추천 top 10 | `serving.hybrid_recommendation` |

---

## 2. 스마트 추천 페이지 `/recommend`

### 레이아웃 구성

```
[GNB]
[스마트 추천 헤더]
[메인 배너 - 추천 top 10 중 인기도 최고 VOD 포스터]
─────────────────────────────────────────────────────
[패턴1 선정이유 텍스트]   ← explanation_tags[0] (섹션 타이틀)
[패턴1 top 10 포스터 가로 스크롤]
─────────────────────────────────────────────────────
[패턴2 선정이유 텍스트]
[패턴2 top 10 포스터 가로 스크롤]
─────────────────────────────────────────────────────
[패턴3 선정이유 텍스트]
[패턴3 top 10 포스터 가로 스크롤]
─────────────────────────────────────────────────────
[패턴4 선정이유 텍스트]
[패턴4 top 10 포스터 가로 스크롤]
─────────────────────────────────────────────────────
[패턴5 선정이유 텍스트]
[패턴5 top 10 포스터 가로 스크롤]
```

### UI 요소별 데이터

#### 메인 배너
- `serving.hybrid_recommendation` 전체 추천 중 인기도(`score`) 최고 VOD 1개
- 필요 데이터: `series_id`, `poster_url`, `asset_nm`

#### 패턴 섹션 (5개)
- **섹션 타이틀** = Hybrid_Layer의 `explanation_tags` 텍스트
  - 예: `"봉준호 감독 작품을 즐겨 보셨어요"` (director affinity 0.92)
  - 예: `"액션 장르를 자주 시청하셨네요"` (genre affinity 0.85)
- **포스터 목록** = 해당 패턴(태그 카테고리) 기반 추천 top 10

| 필드 | DB 컬럼 | 설명 |
|------|---------|------|
| `pattern_rank` | `serving.hybrid_recommendation.rank` | 선호 패턴 순위 (1~5) |
| `pattern_reason` | `serving.hybrid_recommendation.explanation_tags` | 선정이유 텍스트 (JSONB) |
| `series_id` | `vod_id_fk` | VOD 식별자 |
| `poster_url` | `vod.poster_url` | 포스터 이미지 URL |
| `asset_nm` | `vod.asset_nm` | 콘텐츠 제목 |
| `score` | `serving.hybrid_recommendation.score` | 추천 점수 |

### 필요 API

| 엔드포인트 | 설명 | 소스 |
|-----------|------|------|
| `GET /recommend/{user_id}` | 유저 추천 전체 (패턴별 분류 + explanation_tags 포함) | `serving.hybrid_recommendation` |

#### 응답 예시 (`/recommend/{user_id}`)
```json
{
  "user_id": "string",
  "top_vod": {
    "series_id": "string",
    "asset_nm": "string",
    "poster_url": "string"
  },
  "patterns": [
    {
      "pattern_rank": 1,
      "pattern_reason": "봉준호 감독 작품을 즐겨 보셨어요",
      "vod_list": [
        {
          "series_id": "string",
          "asset_nm": "string",
          "poster_url": "string",
          "score": 0.92
        }
      ]
    }
  ]
}
```

> **참고**: `explanation_tags`는 Hybrid_Layer(`serving.hybrid_recommendation.explanation_tags JSONB`)에서 생성되어 API_Server가 그대로 전달한다.

---

## 3. 시리즈 상세 페이지 `/series/:series_id`

### 레이아웃 구성

```
[← 뒤로 가기]
[히어로 영역 - 16:9, 최대 540px]
  ├─ 재생 중: YouTube iframe (autoplay=1)
  ├─ 구매 완료·미재생: ▶ 재생 버튼 오버레이
  └─ 미구매: 자물쇠 아이콘 오버레이
[포스터 썸네일]  [메타데이터]
                [rating / 출시연도 / CT_CL / genre / disp_rtm]
                [+ 찜하기 버튼] [▶ 1화 시청하기 | ▶ 이어보기 | 구매하기]
                [감독 / 출연진 / 줄거리]
──────────────────────────────────────────
[에피소드 목록]
  [썸네일 (진행률 바 포함)] [에피소드명] ["이어보기" 레이블 - 최근 시청 에피소드]
  ...
──────────────────────────────────────────
[유사 콘텐츠 추천]   ← Vector_Search top 10 가로 스크롤
```

### 구매 상태별 UI 분기

| 상태 | 히어로 오버레이 | 하단 버튼 |
|------|--------------|----------|
| **미구매** | 자물쇠 아이콘 | `구매하기` → `/purchase/:series_id` |
| **구매 완료 · 에피소드 시청 기록 없음** | ▶ 재생 버튼 | `▶ 1화 시청하기` → 1화 YouTube 재생 |
| **구매 완료 · 에피소드 시청 기록 있음** | ▶ 재생 버튼 | `▶ 이어보기` → 마지막 시청 에피소드 재생 |
| **재생 중** | YouTube iframe (autoplay) | 버튼 유지 |

> **시청 이력 판단 기준**: `episode_progress` 테이블에서 해당 `series_id`의 레코드 존재 여부.
> 가장 최근 `watched_at` 에피소드가 "이어보기" 대상.

### UI 요소별 데이터

#### 시리즈 헤더
| 필드 | DB 컬럼 | 비고 |
|------|---------|------|
| `poster_url` | `vod.poster_url` | 시리즈 포스터 |
| `asset_nm` | `vod.asset_nm` | 시리즈 제목 |
| `rating` | `vod.rating` | 시청 등급 |
| `release_year` | `vod.release_date` | 출시 연도 |
| `CT_CL` | `vod.CT_CL` | 콘텐츠 분류 |
| `genre` | `vod.genre` | 장르 |
| `disp_rtm` | `vod.disp_rtm` | 영상 길이 (분). `TV드라마` / `TV 연예/오락` CT_CL은 미표시 |
| `director` | `vod.director` | 감독 |
| `cast_lead` | `vod.cast_lead` | 주연 출연진 |
| `smry` | `vod.smry` | 줄거리 |

#### 찜하기 버튼 (토글)
- `+ 찜하기` → 찜 추가 (`wishlist` 테이블 INSERT, `created_at` 기록)
- `♥ 찜완료` → 찜 해제 (`wishlist` 테이블 DELETE)
- 마이페이지 찜 탭에 실시간 반영 (최신 찜 순 정렬)

#### 시청/구매 버튼 (상태 분기)
- **미구매**: `구매하기` → `/purchase/:series_id` 이동
- **구매 완료 · 미시청**: `▶ 1화 시청하기` → `episode_id = {series_id}_ep1` 재생
- **구매 완료 · 시청 기록 있음**: `▶ 이어보기` → 마지막 시청 `episode_id` 재생

#### 에피소드 목록
| 필드 | DB 컬럼 | 설명 |
|------|---------|------|
| `episode_id` | `vod.full_asset_id` | 에피소드 식별자 |
| `asset_nm` | `vod.asset_nm` | 에피소드명 |
| `poster_url` | `vod.poster_url` | 썸네일 |
| `completion_rate` | `episode_progress.completion_rate` | 시청 진행률 (%) — 썸네일 하단 진행바 |
| `watched_at` | `episode_progress.watched_at` | 최근 시청 시각 — 이어보기 에피소드 판별 기준 |

- 클릭 시: 구매 완료 상태이면 해당 화 YouTube 재생. 미구매이면 클릭 무효.
- 현재 재생 중인 에피소드: 파란색 하이라이트 + "재생 중" 레이블
- 마지막 시청 에피소드 (재생 중 아닐 때): "이어보기" 파란색 레이블

#### 유사 콘텐츠 섹션
- 소스: Vector_Search (`vod_meta_embedding` 384차원 코사인 유사도)
- `serving` 테이블에 VOD별 유사 시리즈 top 10 사전 저장
- 필요 데이터: `series_id`, `poster_url`, `asset_nm`

### 필요 API

| 엔드포인트 | 설명 | 소스 |
|-----------|------|------|
| `GET /vod/{series_id}` | 시리즈 메타데이터 전체 | DB (`vod`) |
| `GET /vod/{series_id}/episodes` | 에피소드 목록 | DB (`vod`, 동일 시리즈 필터) |
| `GET /similar/{series_id}` | 유사 콘텐츠 top 10 | `serving` (Vector_Search 적재) |
| `GET /user/{user_id}/series/{series_id}/progress` | 이어보기 에피소드 조회 (`episode_progress` 최신 1건) | DB (`episode_progress`) |
| `POST /user/{user_id}/episode/{episode_id}/progress` | 에피소드 시청 진행률 기록/갱신 | DB (`episode_progress`) |
| `GET /user/{user_id}/purchases/{series_id}` | 구매 여부 + 대여 만료 여부 확인 | DB (`purchase_history`) |
| `POST /user/{user_id}/wishlist` | 찜 추가 | DB (`wishlist`) |
| `DELETE /user/{user_id}/wishlist/{series_id}` | 찜 해제 | DB (`wishlist`) |

---

## 4. 마이 페이지 `/my`

### 레이아웃 구성

```
[GNB - 글로벌 메뉴]
  [사용자 이름] [프로필 전환]  [설정 아이콘]
  [쿠폰 관리] [보유 포인트]
  ─────────────────────────────────────────
  [탭: 시청 내역 | 구매 내역 | 찜]
    [콘텐츠 목록]
  ─────────────────────────────────────────
  [안내: 최근 3개월 시청 내역만 표시, 종료 콘텐츠 미노출]
[Footer]
```

### UI 요소별 데이터

#### 사용자 프로필
| 필드 | 설명 |
|------|------|
| `user_id` | 사용자 식별자 |
| `user_name` | 사용자 이름 |
| `coupon_count` | 보유 쿠폰 수 |
| `point_balance` | 보유 포인트 — 구매 후 재진입 시 차감 반영된 값 표시 |

#### 시청 내역 탭
- 최근 3개월 (`watch_history`)
- 종료된 콘텐츠 제외
- 필요 데이터: `series_id`, `asset_nm`, `poster_url`, `strt_dt`, `completion_rate`
- 콘텐츠 클릭 → `/series/:series_id` 이동 (시청 내역 항목은 기구매 상태이므로 "이어보기" 버튼 표시)

#### 구매 내역 탭
- 필요 데이터: `series_id`, `asset_nm`, `poster_url`, `purchased_at`, `points_used`, `option_type`
- `option_type`: `rental` (48시간 대여) / `permanent` (영구 소장)
- 포인트 단위 표시 (예: 490P, 1,490P)
- 콘텐츠 클릭 → `/series/:series_id` 이동

#### 찜 탭
- 필요 데이터: `series_id`, `asset_nm`, `poster_url`, `created_at`
- **정렬 기준**: `created_at DESC` (가장 최근 찜한 콘텐츠가 상단)
- 콘텐츠 클릭 → `/series/:series_id` 이동
- ♥ 해제 버튼: 클릭 시 목록 즉시 제거 + `wishlist` 테이블 DELETE

### 필요 API

| 엔드포인트 | 설명 | 소스 |
|-----------|------|------|
| `GET /user/{user_id}/profile` | 사용자 프로필 (이름, 쿠폰, 포인트 잔액) | DB |
| `GET /user/{user_id}/points` | 포인트 잔액 + 최근 내역 | DB (`point_history`) |
| `GET /user/{user_id}/history` | 시청 내역 (최근 3개월) | DB (`watch_history`) |
| `GET /user/{user_id}/purchases` | 구매 내역 | DB (`purchase_history`) |
| `GET /user/{user_id}/wishlist` | 찜 목록 (`created_at DESC` 정렬) | DB (`wishlist`) |
| `DELETE /user/{user_id}/wishlist/{series_id}` | 찜 해제 | DB (`wishlist`) |

---

## 5. 구매 페이지 `/purchase/:series_id`

### 레이아웃 구성

```
[모달 오버레이 (전체 화면 dimmed)]
  [X 닫기 버튼]
  [시리즈 포스터 + 시리즈명 + 장르·등급]
  [구매 옵션 선택 (라디오)]
    - 옵션1: 48시간 대여     490 P
    - 옵션2: 영구 소장      1,490 P
  [보유 포인트: N P]
  [NP 결제하기 버튼]
    → 포인트 부족 시: "포인트가 부족합니다." 에러 표시
    → 결제 성공 시: "구매 완료! 시리즈 페이지로 이동합니다..." → 1.5초 후 복귀
```

### 결제 수단
포인트 단일 결제. 별도 결제 수단 선택 없음.

### UI 요소별 데이터

| 필드 | 설명 |
|------|------|
| `series_id` | 시리즈 식별자 |
| `asset_nm` | 시리즈명 |
| `poster_url` | 포스터 이미지 |
| `genre` | 장르 |
| `rating` | 등급 |
| `option_type` | `rental` (48시간 대여, 490P) / `permanent` (영구 소장, 1,490P) |
| `points_used` | 차감 포인트 (선택 옵션 기준) |
| `point_balance` | 현재 보유 포인트 (실시간 표시) |

### 구매 플로우

```
옵션 선택 → [NP 결제하기] 클릭
  ├─ 보유 포인트 ≥ points_used
  │    → point_history INSERT (type='use')
  │    → purchase_history INSERT
  │    → purchasedIds에 series_id 추가
  │    → "구매 완료" 메시지 → 1.5초 후 /series/:id 복귀
  │    → 복귀 후: 버튼이 "구매하기" → "▶ 1화 시청하기"로 자동 전환
  └─ 보유 포인트 < points_used
       → "포인트가 부족합니다." 에러 표시 (페이지 이탈 없음)
```

### 필요 API

| 엔드포인트 | 설명 | 소스 |
|-----------|------|------|
| `GET /vod/{series_id}/purchase-options` | 구매 옵션 조회 (포인트 단위) | DB |
| `POST /purchases` | 구매 처리 (포인트 차감 + 구매 기록) | DB |

#### `POST /purchases` 요청 바디
```json
{
  "user_id": "string",
  "series_id": "string",
  "option_type": "rental | permanent",
  "points_used": 490
}
```

#### `POST /purchases` 응답
```json
{
  "purchase_id": 123,
  "remaining_points": 99510,
  "expires_at": "2026-03-21T15:30:00Z"   // rental만. permanent는 null
}
```

#### 오류 응답
- `402 Payment Required`: 포인트 부족 → Frontend에서 에러 메시지 표시

---

## API 엔드포인트 전체 목록

> API_Server 설계 (`skills/CLAUDE_API_Server.md`) 기준으로 정렬.
> `*` 표시는 기존 설계에 추가 필요한 엔드포인트.

| 메서드 | 엔드포인트 | 페이지 | 설명 | 소스 |
|--------|-----------|--------|------|------|
| GET | `/recommend/{user_id}` | 홈, 스마트 추천 | 개인화 추천 (패턴별 + explanation_tags) | `serving.hybrid_recommendation` |
| GET | `/similar/{series_id}` | 시리즈 상세 | 유사 콘텐츠 top 10 | Vector_Search serving |
| WS/SSE | `/ad/popup` | 공통 | 실시간 광고 트리거 (지자체/제철장터) | `serving.shopping_ad` |
| GET | `/vod/{series_id}` | 시리즈 상세 | 시리즈 메타데이터 | DB (`vod`) |
| POST | `/auth/token` | 공통 | JWT 발급 | 자체 |
| GET | `/home/banner` * | 홈 | 히어로 배너 top 5 (Hybrid top 20 중 score 내림차순) | `serving.hybrid_recommendation` |
| GET | `/home/sections` * | 홈 | 장르별 인기 섹션 CT_CL 4종 × top 20 | `serving.popular_recommendation` |
| GET | `/vod/{series_id}/episodes` * | 시리즈 상세 | 에피소드 목록 | DB (`vod`) |
| GET | `/vod/{series_id}/purchase-options` * | 구매 | 구매 옵션 (포인트 단위) | DB |
| GET | `/user/{user_id}/watching` * | 홈 | 시청 중인 콘텐츠 (strt_dt 최신순 10개, completion_rate 포함) | DB (`watch_history`) |
| GET | `/user/{user_id}/profile` * | 마이페이지 | 사용자 프로필 (이름, 쿠폰, 포인트 잔액) | DB |
| GET | `/user/{user_id}/points` * | 마이페이지 | 포인트 잔액 + 최근 내역 | DB (`point_history`) |
| GET | `/user/{user_id}/history` * | 마이페이지 | 시청 내역 (최근 3개월) | DB (`watch_history`) |
| GET | `/user/{user_id}/purchases` * | 마이페이지 | 구매 내역 | DB (`purchase_history`) |
| GET | `/user/{user_id}/purchases/{series_id}` * | 시리즈 상세 | 특정 시리즈 구매 여부 + 대여 만료 확인 | DB (`purchase_history`) |
| GET | `/user/{user_id}/wishlist` * | 마이페이지 | 찜 목록 (created_at DESC) | DB (`wishlist`) |
| POST | `/user/{user_id}/wishlist` * | 시리즈 상세 | 찜 추가 | DB (`wishlist`) |
| DELETE | `/user/{user_id}/wishlist/{series_id}` * | 시리즈/마이페이지 | 찜 해제 | DB (`wishlist`) |
| GET | `/user/{user_id}/series/{series_id}/progress` * | 시리즈 상세 | 이어보기 에피소드 조회 (watched_at DESC LIMIT 1) | DB (`episode_progress`) |
| POST | `/user/{user_id}/episode/{episode_id}/progress` * | 시리즈 상세 | 에피소드 시청 진행률 기록/갱신 | DB (`episode_progress`) |
| POST | `/purchases` * | 구매 | 구매 처리 (포인트 차감 + purchase_history + point_history 트랜잭션) | DB |
