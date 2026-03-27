# API Server → Frontend 데이터 플로우

> 작성일: 2026-03-27
> 용도: 프론트엔드 UI/UX 시나리오 설계 기준 문서
> 기준: API_Server 브랜치 최신 코드 (라우터 + 서비스 직접 분석)

---

## 인증 흐름 (전역)

```
[앱 최초 로드]
  │
  ▼
AuthGuard: URL ?user_id= 추출 → localStorage 저장
  │
  ▼
POST /auth/token { user_id }
  │
  ▼
← { access_token }  → localStorage 저장
  │
  ▼
이후 모든 API 호출 시 Authorization: Bearer {token} 자동 주입
```

### 인증 상태별 분기

| 상태 | 동작 |
|------|------|
| user_id 있음 + 토큰 발급 성공 | 전체 기능 이용 가능 |
| user_id 없음 | 개인화 섹션/이어보기/추천 미표시, 배너+인기 섹션만 |
| 토큰 만료/401 | 해당 API 섹션 미표시 (자동 갱신 미구현) |

---

## 1. 홈 페이지 `/`

### API 호출 흐름

```
[페이지 마운트]
  │
  ├──→ GET /home/banner          ─→ 히어로 배너 캐러셀
  ├──→ GET /home/sections        ─→ 인기 카테고리 4종
  ├──→ GET /user/me/watching     ─→ 이어보기 섹션 (로그인 전용)
  └──→ GET /home/sections/{uid}  ─→ 개인화 추천 + TOP10 (로그인 전용)
       (4개 병렬 호출)
```

### 1-1. 히어로 배너

**`GET /home/banner`** (JWT 선택적)

```
요청: Authorization: Bearer {token} (선택)
응답: {
  "items": [
    {
      "series_nm": "기생충",          // → 시리즈 상세 링크 키
      "title": "기생충",              // → 배너 제목 텍스트
      "poster_url": "https://...",    // → 배너 배경 이미지
      "category": "영화",             // → 카테고리 뱃지
      "score": 0.95                   // → 정렬 기준 (UI 미표시)
    }
  ],
  "total": 15
}
```

**UI 매핑:**
- 비로그인: popular top 5만 표시
- 로그인: popular 5 + hybrid 10 = 최대 15개 (series_nm 중복 제거)
- 캐러셀 4초 자동 전환
- 포스터 클릭 → `/series/{series_nm}`

---

### 1-2. 인기 카테고리 섹션

**`GET /home/sections`** (인증 불필요)

```
응답: {
  "sections": [
    {
      "ct_cl": "영화",                // → 섹션 타이틀
      "vod_list": [
        {
          "series_nm": "기생충",
          "title": "기생충",          // → 포스터 카드 제목
          "poster_url": "https://...",
          "score": 0.95,
          "rank": 1                   // → UI 미표시 (정렬용)
        }
      ]
    }
  ]
}
```

**UI 매핑:**
- 고정 4개 섹션: 영화 / TV드라마 / TV 연예/오락 / TV애니메이션
- 각 섹션 최대 20개 VOD
- 가로 스크롤, 포스터 카드 클릭 → `/series/{series_nm}`

---

### 1-3. 이어보기 (시청 중인 콘텐츠)

**`GET /user/me/watching?limit=10`** (JWT 필수)

```
응답: {
  "items": [
    {
      "series_nm": "응답하라 1988",   // → 시리즈 상세 링크 키
      "episode_title": "16회",        // → 카드 부제 텍스트
      "poster_url": "https://...",    // → 모바일 카드 이미지
      "completion_rate": 65,          // → 프로그레스바 (%)
      "watched_at": "2026-03-27T..."  // → 정렬 기준 (최신순)
    }
  ],
  "total": 3
}
```

**UI 매핑:**
- 로그인 전용 (비로그인 시 섹션 자체 미표시)
- completion_rate 1~99% 만 표시 (0%=미시청, 100%=완료 제외)
- 카드 하단에 프로그레스바 표시
- 카드 클릭 → `/series/{series_nm}?episode={episode_title}`

---

### 1-4. 개인화 추천 + TOP10

**`GET /home/sections/{user_id}`** (JWT 필수)

```
응답: {
  "sections": [
    // --- 태그 기반 배너 (genre/genre_detail) ---
    {
      "genre": "{user[:5]}님이 좋아할만한 액션",  // → 섹션 타이틀
      "view_ratio": 100,                          // → UI 미표시 (내부 가중치)
      "vod_list": [
        {
          "series_nm": "범죄도시4",
          "asset_nm": "범죄도시4",                // → 포스터 카드 제목
          "poster_url": "https://..."
        }
      ]
    },

    // --- 벡터 유사도 배너 (최대 2개) ---
    {
      "genre": "나의 취향과 비슷한 SF/판타지",    // → 섹션 타이틀
      "vod_list": [
        {
          "series_nm": "인터스텔라",
          "asset_nm": "인터스텔라",
          "poster_url": "https://...",
          "score": 0.87                           // → UI 미표시
        }
      ]
    },

    // --- TOP10 배너 (1개) ---
    {
      "genre": "{user[:5]}님만을 위한 추천 시리즈 TOP10",
      "vod_list": [
        {
          "series_nm": "더 글로리",
          "asset_nm": "더 글로리",
          "poster_url": "https://...",
          "rank": 1,                              // → 순위 뱃지 표시
          "rec_reason": "감독 선호도",            // → 추천 이유 (선택 표시)
          "rec_sentence": "자주 보시는 ..."       // → 추천 문구 (선택 표시)
        }
      ]
    }
  ]
}
```

**UI 매핑:**
- 로그인 전용
- 섹션 구분: `rank` 필드 존재 → TOP10 (순위 뱃지), 없으면 일반 추천 섹션
- `view_ratio` 100→40% 순서로 내림차순 (첫 섹션이 가장 관련도 높음)
- 개인화 데이터 없으면(Cold Start) → null 반환 → 섹션 미표시

---

## 2. 스마트 추천 페이지 `/recommend`

### API 호출 흐름

```
[페이지 마운트]
  │
  └──→ GET /recommend/{user_id}  ─→ 배너 + 패턴별 추천 섹션
```

**`GET /recommend/{user_id}`** (JWT 필수)

```
응답: {
  "user_id": "abc123...",
  "top_vod": {                        // → 풀와이드 메인 배너
    "series_id": "KTH00012345",       // → 시리즈 링크 키 (vod_id_fk)
    "asset_nm": "기생충",             // → 배너 제목
    "poster_url": "https://..."       // → 배너 이미지
  },
  "patterns": [                       // → 패턴별 가로 스크롤 섹션 (최대 5+)
    {
      "pattern_rank": 1,              // → 섹션 순서
      "pattern_reason": "액션 장르를 자주 시청하셨네요",  // → 섹션 타이틀
      "vod_list": [
        {
          "series_id": "KTH00012345",
          "asset_nm": "범죄도시4",    // → 포스터 카드 제목
          "poster_url": "https://...",
          "score": 0.92               // → UI 미표시
        }
      ]
    }
  ],
  "source": "personalized"            // → 상단 인디케이터
}
```

**UI 매핑:**
- `source` 분기:
  - `"personalized"` → 파란색 인디케이터 (개인화 추천)
  - `"popular_fallback"` → 앰버색 인디케이터 + "인기 콘텐츠 기반" 안내 (Cold Start)
- `top_vod` → 풀와이드 배너 (h-[480px])
- `patterns[]` → 각 패턴별 가로 스크롤 섹션
- 포스터 클릭 → `/series/{series_id}`

---

## 3. 시리즈 상세 페이지 `/series/{series_nm}`

### API 호출 흐름

```
[페이지 마운트]
  │
  ├──→ GET /series/{nm}/episodes        ─→ 에피소드 목록
  ├──→ GET /series/{nm}/progress        ─→ 시청 진행률 (로그인)
  ├──→ GET /series/{nm}/purchase-check  ─→ 구매 상태
  │    (3개 병렬 호출)
  │
  ├──[에피소드 선택 시]──→ GET /vod/{asset_id}  ─→ YouTube URL 조회
  │
  ├──[재생 중 30초 간격]──→ POST /series/{nm}/episodes/{asset_nm}/progress
  │                         { completion_rate: 0~100 }
  │
  ├──[찜 토글]──→ POST /wishlist { series_nm }
  │           └→ DELETE /wishlist/{series_nm}
  │
  └──[유사 콘텐츠]──→ GET /similar/{asset_id}?limit=10
```

### 3-1. 에피소드 목록

**`GET /series/{series_nm}/episodes`** (인증 불필요)

```
응답: {
  "series_nm": "응답하라 1988",
  "episodes": [
    {
      "asset_id": "KTH000123",        // → 재생 시 VOD 상세 조회 키
      "episode_title": "1회",          // → 에피소드명
      "category": "TV드라마",          // → UI 미표시
      "poster_url": "https://...",     // → 에피소드 썸네일
      "is_free": false                 // → 무료 뱃지 / 재생 가능 여부
    }
  ],
  "total": 20
}
```

### 3-2. 시청 진행률

**`GET /series/{series_nm}/progress`** (JWT 필수)

```
응답: {
  "series_nm": "응답하라 1988",
  "last_episode": "16회",             // → "이어보기" 대상 에피소드
  "last_completion_rate": 65,          // → 이어보기 진행률
  "episodes": [
    {
      "episode_title": "1회",
      "completion_rate": 100,          // → 에피소드별 프로그레스바
      "watched_at": "2026-03-25T..."
    },
    {
      "episode_title": "16회",
      "completion_rate": 65,
      "watched_at": "2026-03-27T..."
    }
  ]
}
```

**UI 매핑:**
- `last_episode` → 에피소드 리스트에서 "이어보기" 파란색 레이블 표시
- 각 `completion_rate` → 에피소드 썸네일 하단 프로그레스바

### 3-3. 구매 상태

**`GET /series/{series_nm}/purchase-check`** (JWT 필수)

```
응답: {
  "series_nm": "응답하라 1988",
  "purchased": true,                   // → 구매 여부
  "option_type": "rental",             // → "rental" | "permanent"
  "expires_at": "2026-03-29T...",      // → 대여 만료 시각
  "is_expired": false                  // → 만료 여부 (rental만 해당)
}
```

**UI 분기:**

| purchased | is_expired | is_free | 히어로 오버레이 | 하단 버튼 |
|-----------|-----------|---------|--------------|----------|
| false | - | true | 없음 (무료) | `1화 시청하기` |
| false | - | false | 자물쇠 아이콘 | `구매하기` → `/purchase/{series_nm}` |
| true | false | - | 재생 버튼 | 진행률 없으면 `1화 시청하기`, 있으면 `이어보기` |
| true | true | - | 자물쇠 아이콘 | `재구매하기` → `/purchase/{series_nm}` |

### 3-4. VOD 상세 (에피소드 선택 시)

**`GET /vod/{asset_id}`** (인증 불필요)

```
응답: {
  "full_asset_id": "KTH000123",
  "asset_nm": "응답하라 1988 1회",
  "genre": "드라마",
  "ct_cl": "TV드라마",
  "director": "신원호",
  "cast_lead": "이혜리, 류준열",
  "cast_guest": "박보검",
  "smry": "1988년 쌍문동을 배경으로...",
  "rating": "15세",
  "release_date": "2015-11-06",       // → release_year 변환 (2015)
  "poster_url": "https://...",
  "asset_prod": "PPV",                // → "FOD"이면 무료
  "youtube_video_id": "abc123"         // → YouTube IFrame 재생 URL 조합
}
```

**UI 매핑:**
- `youtube_video_id` 존재 → YouTube IFrame API로 재생
- `youtube_video_id` null → 포스터 이미지 fallback
- `rating` → 시청 등급 뱃지
- `release_date` → 연도만 추출 표시
- `cast_lead`, `cast_guest` → 출연진 텍스트
- `smry` → 줄거리 (접기/펼치기)

### 3-5. 진행률 heartbeat

**`POST /series/{series_nm}/episodes/{asset_nm}/progress`** (JWT 필수)

```
요청: { "completion_rate": 65 }     // 0~100 정수
응답: {
  "episode_title": "16회",
  "completion_rate": 65,
  "watched_at": null                // 인메모리 버퍼, 60초 후 DB flush 시 갱신
}
```

- 재생 중 **30초 간격** heartbeat
- 서버 인메모리 버퍼 → 60초 batch flush → DB 반영

### 3-6. 찜 토글

**`POST /wishlist`** (JWT 필수)
```
요청: { "series_nm": "응답하라 1988" }
응답: { "series_nm": "응답하라 1988", "message": "찜 추가 완료" }
```

**`DELETE /wishlist/{series_nm}`** (JWT 필수)
```
응답: { "series_nm": "응답하라 1988", "message": "찜 해제 완료" }
```

- 멱등성: 이미 찜한 시리즈 재요청 시 무시 (ON CONFLICT DO NOTHING)

### 3-7. 유사 콘텐츠

**`GET /similar/{asset_id}?limit=10`** (인증 불필요)

```
응답: {
  "base_asset_id": "KTH000123",
  "items": [
    {
      "asset_id": "KTH000456",
      "rank": 1,
      "score": 0.89,                  // → UI 미표시
      "title": "미생",                // → 포스터 카드 제목
      "genre": "드라마",
      "poster_url": "https://..."
    }
  ],
  "total": 10,
  "source": "vector_similarity"        // → "vector_similarity" | "genre_fallback"
}
```

---

## 4. 마이 페이지 `/my`

### API 호출 흐름

```
[페이지 마운트]
  │
  ├──→ GET /user/me/profile       ─→ 프로필 헤더
  ├──→ GET /user/me/history       ─→ 시청 내역 탭
  ├──→ GET /user/me/purchases     ─→ 구매 내역 탭
  ├──→ GET /user/me/wishlist      ─→ 찜 목록 탭
  └──→ GET /user/me/points        ─→ 포인트 잔액
       (5개 병렬 호출)
  │
  └──[찜 삭제]──→ DELETE /wishlist/{series_nm}
```

### 4-1. 프로필

**`GET /user/me/profile`** (JWT 필수)

```
응답: {
  "user_name": "abc12",              // → 프로필 이름 (sha2_hash 앞 5자)
  "point_balance": 99510             // → "보유 포인트: 99,510P"
}
```

### 4-2. 시청 내역 탭

**`GET /user/me/history?limit=50`** (JWT 필수)

```
응답: {
  "items": [
    {
      "series_nm": "응답하라 1988",
      "episode_title": "16회",
      "poster_url": "https://...",
      "completion_rate": 65,          // → 프로그레스바
      "watched_at": "2026-03-27T..."  // → "3월 27일 시청"
    }
  ],
  "total": 12
}
```

- watch_history + episode_progress UNION (series_nm 중복 제거, 최신만)
- 클릭 → `/series/{series_nm}`

### 4-3. 구매 내역 탭

**`GET /user/me/purchases?limit=50`** (JWT 필수)

```
응답: {
  "items": [
    {
      "series_nm": "기생충",
      "option_type": "permanent",     // → "영구 소장" | "48시간 대여"
      "points_used": 1490,            // → "1,490P"
      "purchased_at": "2026-03-20T...",
      "expires_at": null              // → permanent는 null, rental은 만료일
    }
  ],
  "total": 5
}
```

### 4-4. 찜 목록 탭

**`GET /user/me/wishlist`** (JWT 필수)

```
응답: {
  "items": [
    {
      "series_nm": "더 글로리",
      "poster_url": "https://...",
      "created_at": "2026-03-25T..."  // → 정렬 기준 (최신순)
    }
  ],
  "total": 8
}
```

- 정렬: created_at DESC (최근 찜한 것이 상단)
- 하트 아이콘 클릭 → DELETE /wishlist/{series_nm} → 목록에서 즉시 제거

### 4-5. 포인트 내역

**`GET /user/me/points?limit=20`** (JWT 필수)

```
응답: {
  "balance": 99510,                   // → 잔액 (= point_balance)
  "history": [
    {
      "type": "use",                  // → "use" (사용) | "earn" (적립)
      "amount": 490,                  // → "-490P" 또는 "+490P"
      "description": "응답하라 1988 48시간 대여",
      "created_at": "2026-03-25T..."
    }
  ]
}
```

---

## 5. 구매 페이지 `/purchase/{series_nm}`

### API 호출 흐름

```
[페이지 마운트]
  │
  ├──→ GET /series/{nm}/purchase-options  ─→ 구매 옵션 표시
  └──→ GET /user/me/points               ─→ 보유 포인트 표시
       (2개 병렬 호출)
  │
  └──[결제 클릭]──→ POST /purchases  ─→ 성공/실패 처리
```

### 5-1. 구매 옵션

**`GET /series/{series_nm}/purchase-options`** (인증 불필요)

```
응답: {
  "series_nm": "응답하라 1988",
  "is_free": false,                    // → true면 "무료 시청 가능" 안내
  "options": [
    {
      "option_type": "rental",         // → "48시간 대여"
      "points": 490,                   // → "490P"
      "duration": "48h"                // → "48시간"
    },
    {
      "option_type": "permanent",      // → "영구 소장"
      "points": 1490,                  // → "1,490P"
      "duration": null
    }
  ]
}
```

**UI 분기:**
- `is_free: true` → 구매 UI 대신 "무료 시청 가능" 안내
- `is_free: false` → 옵션 라디오 버튼 + 결제 버튼

### 5-2. 결제 처리

**`POST /purchases`** (JWT 필수)

```
요청: {
  "series_nm": "응답하라 1988",
  "option_type": "rental",
  "points_used": 490
}

성공 응답 (200):
{
  "series_nm": "응답하라 1988",
  "option_type": "rental",
  "points_used": 490,
  "remaining_points": 99020,          // → 잔액 업데이트
  "expires_at": "2026-03-29T..."      // → rental만 (permanent는 null)
}

실패 응답 (402):
{
  "error": { "code": "INSUFFICIENT_POINTS", "message": "포인트가 부족합니다" }
}
```

**UI 분기:**
- 성공 → "구매 완료!" 메시지 → **1.5초 후** `/series/{series_nm}` 자동 리다이렉트
- 포인트 부족 → 빨간 경고 메시지 + 결제 버튼 비활성화
- 이미 구매됨 → 포인트 미차감, 기존 구매 정보 반환

---

## 6. GNB (전역 컴포넌트)

### API 호출 흐름

```
[레이아웃 마운트]
  │
  └──→ GET /user/me/notifications  ─→ 알림 벨 뱃지 + 드롭다운

[검색어 입력 (300ms debounce)]
  │
  └──→ GET /vod/search?q={query}   ─→ 검색 결과 드롭다운

[알림 개별 삭제]
  └──→ DELETE /user/me/notifications/{id}

[알림 읽음]
  └──→ PATCH /user/me/notifications/{id}/read

[알림 전체 읽음]
  └──→ POST /user/me/notifications/read-all
```

### 6-1. 통합 검색

**`GET /vod/search?q={query}`** (인증 불필요)

```
응답: {
  "items": [
    {
      "series_nm": "기생충",
      "asset_nm": "기생충",            // → 검색 결과 텍스트
      "genre": "드라마/스릴러",
      "ct_cl": "영화",
      "poster_url": "https://..."      // → 검색 결과 썸네일
    }
  ],
  "total": 3
}
```

**검색 기능:**
- 제목 / 출연진 / 감독 / 장르 통합 검색
- 초성 검색 지원 (ㄱㅅㅊ → 기생충)
- 에피소드 파싱 ("응답하라 3화" → 해당 에피소드 직접 표시)
- 최대 **8개** 결과
- 300ms debounce
- 결과 클릭 → `/series/{series_nm}`
- ESC 키 → 검색 닫기

### 6-2. 알림

**`GET /user/me/notifications`** (JWT 필수)

```
응답: {
  "items": [
    {
      "notification_id": 42,
      "type": "reservation",           // → 알림 아이콘 분기
      "title": "응답하라 1988 16회",   // → 알림 제목
      "message": "채널 25번에서 ...",  // → 알림 본문
      "image_url": "https://...",      // → 알림 썸네일 (선택)
      "read": false,                   // → 미읽음 스타일
      "created_at": "2026-03-27T..."
    }
  ],
  "total": 5,
  "unread_count": 2                    // → 벨 아이콘 뱃지 숫자
}
```

---

## 7. 광고 팝업 시스템 (WebSocket)

### 연결 흐름

```
[시리즈 상세 페이지 마운트 + 영상 재생]
  │
  ▼
WS 연결: /ad/popup?user_id={id}
  │
  ├──[500ms 간격]──→ 송신: { type: "playback_update", vod_id, time_sec }
  │
  ├──[서버 응답]──← 수신: { type: "ad_popup", ad_type, vod_id, time_sec, data }
  │                                      │
  │                    ┌─────────────────┤
  │                    ▼                 ▼
  │              "local_gov"      "seasonal_market"
  │              (지자체 팝업)     (제철장터 연계)
  │
  ├──[사용자 액션]──→ 송신: { type: "ad_action", action, vod_id }
  │                          action: "dismiss" | "minimize" | "reopen" | "reserve_watch"
  │
  ├──[액션 응답]──← 수신: { type: "ad_response", action, vod_id, message }
  │
  └──[시청예약 알림]──← 수신: { type: "reservation_alert", channel, program_name, message }
```

### 광고 팝업 데이터

```
ad_popup 수신 데이터:
{
  "type": "ad_popup",
  "ad_type": "local_gov",              // → 팝업 타입 분기
  "vod_id": "KTH000123",
  "time_sec": 120,
  "data": {
    "shopping_ad_id": "ad_001",
    "ad_category": "tourism",          // → "tourism" (관광) | "food" (음식)
    "signal_source": "clip",
    "score": 0.85,
    "ad_image_url": "https://...",     // → 팝업 이미지
    "product_name": "전주 한옥마을",    // → 팝업 제목
    "channel": "25",                   // → 채널 번호 (제철장터)

    // seasonal_market인 경우 ad_hints에서 언팩:
    "broadcast_date": "2026-03-28",    // → 방송 날짜 표시
    "start_time": "14:00",            // → 방송 시작 시간
    "end_time": "15:00"               // → 방송 종료 시간
  }
}
```

**UI 분기:**

| ad_type | 팝업 내용 | 사용자 액션 |
|---------|----------|-----------|
| `local_gov` | 지자체 축제/관광 GIF 이미지 | 닫기 / 최소화 |
| `seasonal_market` | 제철장터 상품 + 방송 시간 | **시청예약** / 닫기 / 최소화 |

**타이밍:**
- 팝업 표시 → **10초 후 자동 최소화**
- 최소화 → 우하단 작은 아이콘 (클릭 시 reopen)
- 토스트 알림 → **3초 후 자동 제거**
- WebSocket 끊김 → exponential backoff 재연결 (최대 10회)

---

## 8. 시청예약 시스템

### API 호출 흐름

```
[광고 팝업에서 "시청예약" 클릭]
  │
  └──→ WebSocket ad_action { action: "reserve_watch", vod_id }
       │
       ▼
  ←── ad_response { action: "reserve_watch", message: "시청예약 완료" }
       │
       ▼
  [서버 30초 주기 체크: alert_at ≤ NOW()]
       │
       ▼
  ←── reservation_alert { channel: 25, program_name: "제철장터", message: "채널 25번에서..." }
```

**REST API (마이페이지 등에서 직접 관리):**

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/reservations` | 시청예약 등록 |
| GET | `/reservations` | 미알림 예약 목록 |
| DELETE | `/reservations/{id}` | 예약 취소 |

```
POST /reservations 요청:
{
  "channel": 25,
  "program_name": "제철장터",
  "alert_at": "2026-03-28T14:00:00+09:00"
}

응답:
{
  "reservation_id": 7,
  "channel": 25,
  "program_name": "제철장터",
  "alert_at": "2026-03-28T14:00:00+09:00"
}
```

---

## 부록: API 전체 목록 요약

### 인증 불필요 (Public)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| POST | `/auth/token` | JWT 발급 |
| GET | `/health` | 서버 상태 확인 |
| GET | `/home/banner` | 히어로 배너 (JWT 있으면 개인화 추가) |
| GET | `/home/sections` | 인기 카테고리 4종 |
| GET | `/vod/{asset_id}` | VOD 상세 메타데이터 |
| GET | `/vod/search?q=` | 통합 검색 |
| GET | `/series/{nm}/episodes` | 에피소드 목록 |
| GET | `/series/{nm}/purchase-options` | 구매 옵션 |
| GET | `/similar/{asset_id}` | 유사 콘텐츠 |

### 인증 필수 (JWT Bearer)

| 메서드 | 경로 | 용도 |
|--------|------|------|
| GET | `/home/sections/{user_id}` | 개인화 추천 + TOP10 |
| GET | `/recommend/{user_id}` | 스마트 추천 패턴 |
| GET | `/user/me/watching` | 이어보기 |
| GET | `/user/me/profile` | 프로필 |
| GET | `/user/me/points` | 포인트 잔액 + 내역 |
| GET | `/user/me/history` | 시청 내역 |
| GET | `/user/me/purchases` | 구매 내역 |
| GET | `/user/me/wishlist` | 찜 목록 |
| GET | `/series/{nm}/progress` | 시청 진행률 |
| GET | `/series/{nm}/purchase-check` | 구매 확인 |
| POST | `/series/{nm}/episodes/{nm}/progress` | 진행률 heartbeat |
| POST | `/purchases` | 포인트 결제 |
| POST | `/wishlist` | 찜 추가 |
| DELETE | `/wishlist/{series_nm}` | 찜 해제 |
| GET | `/user/me/notifications` | 알림 목록 |
| PATCH | `/user/me/notifications/{id}/read` | 알림 읽음 |
| POST | `/user/me/notifications/read-all` | 전체 읽음 |
| DELETE | `/user/me/notifications/{id}` | 알림 삭제 |
| POST | `/reservations` | 시청예약 등록 |
| GET | `/reservations` | 예약 목록 |
| DELETE | `/reservations/{id}` | 예약 취소 |
| WS | `/ad/popup?user_id=` | 실시간 광고 WebSocket |

### 에러 응답 공통 형식

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "사용자 표시 메시지"
  }
}
```

| HTTP 상태 | 코드 | 상황 |
|-----------|------|------|
| 401 | UNAUTHORIZED | 토큰 없음/만료 |
| 402 | INSUFFICIENT_POINTS | 포인트 부족 |
| 403 | RENTAL_EXPIRED | 대여 만료 |
| 404 | NOT_FOUND | 리소스 없음 |
| 409 | ALREADY_EXISTS | 중복 (찜 등) |

### 백그라운드 프로세스 (UI 직접 호출 X)

| 주기 | 동작 | 영향 |
|------|------|------|
| 60초 | progress buffer flush | heartbeat 데이터가 DB에 반영됨 |
| 30초 | reservation check | 예약 알림 WebSocket 전송 + notifications INSERT |
