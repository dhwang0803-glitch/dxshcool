# API 협의 사항

> Frontend ↔ API_Server 간 조율이 필요한 항목 모음.
> 작성일: 2026-03-19
> 참조: `docs/UI_SCENARIO.md`, `skills/CLAUDE_API_Server.md`

---

## 협의 상태 범례

| 상태 | 의미 |
|------|------|
| 🔴 미협의 | 아직 논의 안 됨 |
| 🟡 협의 중 | 논의 진행 중 |
| 🟢 확정 | 합의 완료 |

---

## 1. 신규 엔드포인트 추가 요청

> `skills/CLAUDE_API_Server.md` 기존 설계에 없는 엔드포인트. API_Server 팀에 추가 구현 요청 필요.

| 상태 | 엔드포인트 | 필요 페이지 | 설명 |
|------|-----------|------------|------|
| 🔴 | `GET /home/banner` | 홈 | Hybrid top 20 중 score 내림차순 top 5 반환 (캐러셀용, 비로그인 시 popular_recommendation 대체) |
| 🔴 | `GET /home/sections` | 홈 | CT_CL 4종(영화/TV드라마/TV 연예·오락/TV애니메이션) × top 20 반환 (`serving.popular_recommendation`) |
| 🔴 | `GET /user/{user_id}/watching` | 홈 | 시청 중인 콘텐츠 목록 (completion_rate 포함) |
| 🔴 | `GET /vod/{series_id}/episodes` | 시리즈 상세 | 동일 시리즈 에피소드 목록 |
| 🔴 | `GET /user/{user_id}/series/{series_id}/progress` | 시리즈 상세 | 해당 시리즈에서 마지막으로 시청한 에피소드 ID + completion_rate (이어보기 버튼용) |
| 🔴 | `POST /user/{user_id}/episode/{episode_id}/progress` | 시리즈 상세 | 에피소드 시청 진행률 기록 (재생 시작·종료·주기적 호출) |
| 🔴 | `GET /vod/{series_id}/purchase-options` | 구매 | 구매 옵션 (포인트 단위: rental=490P, permanent=1490P) |
| 🔴 | `GET /user/{user_id}/profile` | 마이페이지 | 사용자 이름, 쿠폰, 포인트 잔액 |
| 🔴 | `GET /user/{user_id}/points` | 마이페이지 | 포인트 잔액 + 최근 point_history 내역 |
| 🔴 | `GET /user/{user_id}/history` | 마이페이지 | 시청 내역 (최근 3개월) |
| 🔴 | `GET /user/{user_id}/purchases` | 마이페이지 | 구매 내역 (포인트 단위 금액 포함) |
| 🔴 | `GET /user/{user_id}/purchases/{series_id}` | 시리즈 상세 | 특정 시리즈 구매 여부 + rental 만료 여부 확인 |
| 🔴 | `GET /user/{user_id}/wishlist` | 마이페이지, 시리즈 상세 | 찜 목록 (created_at DESC 정렬) |
| 🔴 | `POST /user/{user_id}/wishlist` | 시리즈 상세 | 찜 추가 |
| 🔴 | `DELETE /user/{user_id}/wishlist/{series_id}` | 시리즈 상세, 마이페이지 | 찜 해제 |
| 🔴 | `POST /purchases` | 구매 | 구매 처리 (포인트 차감 · purchase_history · point_history 트랜잭션) |

---

## 2. 기존 엔드포인트 응답 형식 협의

### 2-1. `GET /recommend/{user_id}` — 응답 구조 확장

**현재 설계** (`skills/CLAUDE_API_Server.md`): CF_Engine 결과만 반환.

**Frontend 요청**: 스마트 추천 페이지 + 홈 개인화 섹션 모두에서 사용하므로, Hybrid_Layer의 `explanation_tags`를 포함한 패턴별 그룹핑 구조 필요.

| 상태 | 항목 |
|------|------|
| 🔴 | 응답에 `explanation_tags` (JSONB → 문자열 배열) 포함 여부 |
| 🔴 | 패턴별 그룹핑 형태로 반환할지, flat list로 반환 후 Frontend에서 그룹핑할지 |
| 🔴 | 홈용(top 10)과 스마트 추천용(패턴 5개 × top 10)을 같은 엔드포인트로 처리할지, 분리할지 |

**Frontend 제안 응답 형식:**
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

---

### 2-2. `GET /similar/{series_id}` — 경로 파라미터명 통일

**현재 설계**: `/similar/{asset_id}` (asset_id 사용)

**Frontend 사용**: `series_id` 기준으로 시리즈 상세 페이지에서 호출.

| 상태 | 항목 |
|------|------|
| 🔴 | `asset_id` vs `series_id` 파라미터명 통일 필요 (`vod.full_asset_id`가 기준인지 확인) |

---

### 2-3. `POST /purchases` — 포인트 결제 처리

**현재 구현**: 결제 수단을 포인트로 단일화. `payment_method` 필드 제거.

| 상태 | 항목 |
|------|------|
| 🔴 | 포인트 환율 정책 확정 (현재 Mock: 원 ÷ 10 = 포인트, 4,900원 → 490P / 14,900원 → 1,490P) |
| 🔴 | 포인트 부족 시 응답 코드 확정 (`402 Payment Required` 제안) |
| 🔴 | `purchase_history` + `point_history` 동시 INSERT 트랜잭션 처리 방식 |
| 🔴 | 대여(`rental`) 만료 시각 계산 기준 (purchased_at + 48h) 및 만료 후 재생 차단 방식 |

**Frontend 제안 요청 바디:**
```json
{
  "user_id": "string",
  "series_id": "string",
  "option_type": "rental | permanent",
  "points_used": 490
}
```

**Frontend 제안 응답:**
```json
{
  "purchase_id": 123,
  "remaining_points": 99510,
  "expires_at": "2026-03-21T15:30:00Z"
}
```

---

### 2-5. `GET /vod/{series_id}` — 응답 필드 확인

**Frontend 필요 필드**: `poster_url`, `asset_nm`, `rating`, `release_date`, `CT_CL`, `genre`, `disp_rtm`, `director`, `cast_lead`, `smry`

| 상태 | 항목 |
|------|------|
| 🔴 | `disp_rtm` — TV드라마/TV 연예/오락은 응답에서 제외할지, Frontend에서 필터링할지 |
| 🔴 | `release_date` 전체 반환 후 Frontend에서 연도만 추출할지, API에서 연도만 반환할지 |

---

## 3. WebSocket `/ad/popup` 프로토콜 협의

**현재 설계**: WS/SSE로 광고 트리거 전송 (Shopping_Ad → API_Server → Frontend).

| 상태 | 항목 |
|------|------|
| 🔴 | WebSocket vs SSE 최종 방식 결정 |
| 🔴 | 메시지 payload 구조 정의 (vod_id, time_sec, ad_type, ad_image_url, action_type 등) |
| 🔴 | Frontend → API_Server 광고 액션 결과 전송 방식 (같은 WS 채널 vs 별도 REST POST) |
| 🔴 | 광고 타입 구분값 정의: `지자체(local_gov)` / `제철장터(seasonal_market)` |

**Frontend 제안 메시지 형식:**
```json
{
  "vod_id": "string",
  "time_sec": 120,
  "ad_type": "local_gov | seasonal_market",
  "ad_image_url": "string",
  "action_buttons": ["채널이동", "시청예약", "닫기"]
}
```

---

## 4. 인증(JWT) 관련 협의

| 상태 | 항목 |
|------|------|
| 🔴 | `POST /auth/token` 요청 바디 형식 (user_id/password? OAuth?) |
| 🔴 | JWT 토큰 저장 위치: localStorage vs httpOnly Cookie |
| 🔴 | 토큰 만료 시간 및 refresh token 사용 여부 |
| 🔴 | 비로그인 유저 접근 시 동작 정의 (홈 시청중/개인화 섹션 미표시 처리) |

---

## 5. Database_Design 브랜치 협의 항목

> 현재 스키마에 없는 테이블. `Database_Design` 브랜치에 추가 요청 필요.

### 5-1. `wishlist` 테이블

| 상태 | 항목 |
|------|------|
| 🔴 | `public.wishlist` 테이블 신규 생성 |
| 🔴 | CF_Engine 피드백 신호로 활용 여부 (찜 = 암묵적 긍정 피드백, watch_history보다 약한 가중치) |

**제안 DDL:**
```sql
CREATE TABLE public.wishlist (
  user_id     VARCHAR(64)  NOT NULL,
  series_id   VARCHAR(64)  NOT NULL,
  created_at  TIMESTAMPTZ  DEFAULT now(),
  PRIMARY KEY (user_id, series_id)
);
```

**CF_Engine 활용 검토:**
- `watch_history` (강한 신호, 가중치 1.0) + `wishlist` (중간 신호, 가중치 0.5)를 함께 ALS 행렬 분해 입력으로 사용하면 추천 품질 향상 가능
- CF_Engine 브랜치 담당자와 별도 협의 필요

---

### 5-2. `episode_progress` 테이블

에피소드별 시청 진행률을 저장. 시리즈 상세 진입 시 "1화 시청하기" vs "이어보기" 분기 및 에피소드 목록의 진행률 바 표시에 사용.

| 상태 | 항목 |
|------|------|
| 🔴 | `public.episode_progress` 테이블 신규 생성 |
| 🔴 | 기존 `watch_history`(시리즈 단위)와 역할 분리 확인 — `watch_history`는 홈 이어보기·마이페이지용, `episode_progress`는 시리즈 상세 플레이어용 |
| 🔴 | `completion_rate` 업데이트 호출 주기 결정 (재생 종료 시 1회 vs 30초마다 heartbeat) |
| 🔴 | `episode_progress` 기록 시 `watch_history.strt_dt` 동기 갱신 여부 (두 테이블 일관성) |

**제안 DDL:**
```sql
CREATE TABLE public.episode_progress (
  user_id         VARCHAR(64)  NOT NULL,
  episode_id      VARCHAR(128) NOT NULL,
  series_id       VARCHAR(64)  NOT NULL,
  completion_rate SMALLINT     NOT NULL DEFAULT 0 CHECK (completion_rate BETWEEN 0 AND 100),
  watched_at      TIMESTAMPTZ  DEFAULT now(),   -- 마지막 시청 시각 (이어보기 정렬 기준)
  PRIMARY KEY (user_id, episode_id)
);
CREATE INDEX idx_ep_progress_series ON public.episode_progress (user_id, series_id, watched_at DESC);
```

**API_Server 연동:**
- `GET /user/{user_id}/series/{series_id}/progress`
  - `episode_progress`에서 `user_id + series_id` 조건, `watched_at DESC LIMIT 1` 조회
  - 없으면 `null` 반환 → Frontend에서 "1화 시청하기" 표시
  - 있으면 `{ episode_id, completion_rate }` 반환 → "이어보기" 표시
- `POST /user/{user_id}/episode/{episode_id}/progress`
  - `completion_rate`, `series_id` body로 전달
  - `ON CONFLICT (user_id, episode_id) DO UPDATE SET completion_rate=..., watched_at=now()`

**Frontend 호출 시점:**
- 시리즈 상세 진입 시 → `GET` 호출로 이어보기 에피소드 결정
- 재생 버튼 클릭 시 → `POST` 호출 (completion_rate=0 또는 기존값 유지)
- 재생 종료·페이지 이탈 시 → `POST` 호출로 최종 completion_rate 저장

---

### 5-3. `purchase_history` 테이블

| 상태 | 항목 |
|------|------|
| 🔴 | `public.purchase_history` 테이블 신규 생성 |
| 🔴 | 대여(48시간) 만료 처리 방식 — DB 컬럼으로 만료시각 관리 vs API_Server에서 만료 체크 |
| 🔴 | 구매 완료 후 재생 권한 확인 엔드포인트 (`GET /user/{user_id}/purchases/{series_id}`) 추가 여부 |

**제안 DDL:**
```sql
CREATE TABLE public.purchase_history (
  purchase_id   SERIAL       PRIMARY KEY,
  user_id       VARCHAR(64)  NOT NULL,
  series_id     VARCHAR(64)  NOT NULL,
  option_type   VARCHAR(16)  NOT NULL CHECK (option_type IN ('rental', 'permanent')),
  price         INTEGER      NOT NULL,
  purchased_at  TIMESTAMPTZ  DEFAULT now(),
  expires_at    TIMESTAMPTZ,          -- 대여(48시간)만 사용, 영구 소장은 NULL
  UNIQUE (user_id, series_id, purchased_at)
);
```

**API_Server 연동:**
- `POST /purchases` 호출 시 이 테이블에 INSERT
- `GET /user/{user_id}/purchases` 조회 시 이 테이블 SELECT
- 대여 만료 체크: `expires_at > now()` 조건 추가

---

### 5-4. `point_history` 테이블

결제 수단을 포인트로 통일. 구매 시 포인트 차감 내역을 기록한다.

| 상태 | 항목 |
|------|------|
| 🔴 | `public.point_history` 테이블 신규 생성 |
| 🔴 | 포인트 환율 정책 확정 (현재 Mock: 원 ÷ 10 = 포인트, 예: 4,900원 → 490P) |
| 🔴 | 포인트 충전 엔드포인트 및 충전 단위 정의 |
| 🔴 | `GET /user/{user_id}/points` — 잔액 + 내역 반환 엔드포인트 추가 여부 |

**제안 DDL:**
```sql
CREATE TABLE public.point_history (
  history_id   SERIAL       PRIMARY KEY,
  user_id      VARCHAR(64)  NOT NULL,
  type         VARCHAR(8)   NOT NULL CHECK (type IN ('use', 'earn')),
  amount       INTEGER      NOT NULL,        -- 차감/적립 포인트 (양수)
  description  VARCHAR(256) NOT NULL,        -- 예: '파묘 48시간 대여'
  created_at   TIMESTAMPTZ  DEFAULT now()
);
```

**API_Server 연동:**
- `POST /purchases` 처리 시 `purchase_history` INSERT와 함께 `point_history` INSERT (트랜잭션으로 묶음)
- `GET /user/{user_id}/points` — 잔액(`SUM CASE WHEN type='earn'`) + 최근 내역 반환
- 포인트 부족 시 API에서 `402 Payment Required` 반환 → Frontend 에러 처리

---

## 6. 공통 응답 형식 협의

| 상태 | 항목 |
|------|------|
| 🔴 | 공통 에러 응답 형식 정의 (`{"error": "...", "code": ...}` 등) |
| 🔴 | 페이지네이션 방식: offset/limit vs cursor |
| 🔴 | CORS 허용 origin 범위 (개발/프로덕션 분리) |
