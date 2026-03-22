# API_Server 기술 명세서 (Notion 업로드용)

> 작성일: 2026-03-20 | 작성자: 조장(dhwang0803)
> 이 문서는 Notion 페이지로 변환하여 팀 전체에 공유할 기술 명세서입니다.
> 각 엔드포인트별 기능 개요, 기본 기능, 예외사항, 제약사항, 의존성을 포함합니다.

---

## 1. 시스템 개요

### 1-1. 아키텍처

```
셋톱박스(Frontend) ←→ FastAPI(API_Server) ←→ PostgreSQL(VPC)
                          ↑                        ↑
                     WebSocket                  asyncpg 풀
                    (광고 팝업)                (max_size=10)
```

### 1-2. 인증 방식

| 항목 | 내용 |
|------|------|
| 방식 | IPTV 셋톱박스 자동 로그인 |
| 토큰 | JWT (HS256, 만료 없음) |
| 식별자 | `sha2_hash` (user 테이블 PK) |
| 발급 | 셋톱박스 전원 ON → `POST /auth/token` 자동 호출 |
| 비로그인 | 고려 불필요 (사이트 진입 = 즉시 로그인) |

### 1-3. 공통 규칙

| 규칙 | 설명 |
|------|------|
| 식별자 체계 | 시리즈: `series_nm`, 에피소드: `asset_nm` (내부 ID 미노출) |
| 에러 응답 | `{"error": {"code": "ERROR_CODE", "message": "한글 메시지"}}` |
| 페이지네이션 | 25건/페이지, 페이지 번호 버튼 (1,2,3,4,5) |
| 에피소드 검색 | 출연진 초성검색 + 회차 숫자 검색 |
| CORS | `localhost:3000` (Cloud Run 배포 시 조정) |
| 포인트 환율 | Mock 기준 유지 (대여 490P, 영구 1490P) |
| 대여 만료 | 48시간 |
| FOD 무료 | `asset_prod='FOD'` → `is_free=true` |

---

## 2. 엔드포인트 상세

---

### 2-1. `POST /auth/token` — JWT 발급

**기능 개요**: 셋톱박스에 등록된 유저 ID(sha2_hash)로 만료 없는 JWT 토큰 발급

**기본 기능**:
- 요청: `{ "user_id": "sha2_hash값" }`
- user 테이블에서 sha2_hash 존재 확인
- 존재하면 JWT 발급 (payload: `{ "sub": "sha2_hash값" }`, 만료 없음)
- 응답: `{ "access_token": "eyJ...", "token_type": "bearer" }`

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `USER_NOT_FOUND` | 404 | sha2_hash가 user 테이블에 없음 |

**제약사항**:
- `JWT_SECRET_KEY` 환경변수 필수 (미설정 시 서버 기동 실패)
- 비밀번호/OAuth 없음 — sha2_hash만으로 인증

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public."user"` | sha2_hash 존재 확인 |
| 다운스트림 | 전체 인증 필요 엔드포인트 | Bearer 토큰 |

---

### 2-2. `GET /home/banner` — 히어로 배너

**기능 개요**: 홈 화면 상단 히어로 배너 5개 반환 (개인화 추천 → 인기 fallback)

**기본 기능**:
- hybrid_recommendation 테이블에서 유저 기반 추천 조회 시도
- 없으면 popular_recommendation에서 인기순 fallback
- series_nm 기준 중복 제거 후 top 5 반환
- 응답 필드: `series_nm`, `title`, `poster_url`, `category`, `score`

**예외사항**:
- 추천/인기 데이터 없으면 빈 배열 반환 (에러 아님)

**제약사항**:
- hybrid_recommendation 미적재 시 항상 popular fallback

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `serving.hybrid_recommendation` | 개인화 추천 (primary) |
| 업스트림 | `serving.popular_recommendation` | 인기순 (fallback) |
| 업스트림 | `public.vod` | poster_url, series_nm 조회 |

---

### 2-3. `GET /home/sections` — CT_CL별 인기 섹션

**기능 개요**: CT_CL 4종(영화/TV드라마/TV 연예·오락/TV애니메이션) × top 20 반환

**기본 기능**:
- popular_recommendation 테이블에서 ct_cl별 그룹핑
- 각 ct_cl당 rank 순서로 20개
- 응답: `{ "sections": [{ "ct_cl": "영화", "vod_list": [...] }] }`

**예외사항**:
- 특정 ct_cl 데이터 없으면 해당 섹션 빈 배열

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `serving.popular_recommendation` | CT_CL별 Top-N |
| 업스트림 | `public.vod` | 메타데이터 JOIN |

---

### 2-4. `GET /vod/{asset_id}` — VOD 상세

**기능 개요**: 개별 VOD의 상세 메타데이터 반환

**기본 기능**:
- full_asset_id 기준 PK 조회
- `release_date` → `release_year` (연도 int만 반환)
- `asset_prod == 'FOD'` → `is_free: true` (무료 콘텐츠 여부)
- 응답 필드: `asset_id`, `title`, `genre`, `category`, `director`, `cast_lead`, `cast_guest`, `summary`, `rating`, `release_year`, `poster_url`, `is_free`

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `VOD_NOT_FOUND` | 404 | asset_id가 vod 테이블에 없음 |

**제약사항**:
- 인증 불필요 (공개 엔드포인트)
- `full_asset_id`는 내부 ID이므로 Frontend에서는 `series_nm` + `asset_nm` 조합으로 접근

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.vod` | 전체 메타데이터 |

---

### 2-5. `GET /series/{series_nm}/episodes` — 에피소드 목록

**기능 개요**: 시리즈의 에피소드 목록 반환 (중복 제거 적용)

**기본 기능**:
- `series_nm` 기준 vod 테이블에서 에피소드 조회
- `DISTINCT ON(asset_nm)` + provider 우선순위 (`kth > cjc > hcn > 기타`)로 중복 제거
- 각 에피소드에 `is_free` 포함
- 응답 필드: `episode_title`, `category`, `poster_url`, `is_free`

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `SERIES_NOT_FOUND` | 404 | series_nm에 해당하는 에피소드 없음 |

**제약사항**:
- 동일 에피소드가 다른 provider에서 중복 존재 (예: kth, cjc 동시 제공) → provider 우선순위로 1개만 반환
- "아는형님" 등 수백 회차 시리즈 → 페이지네이션 필수 (25건/페이지)
- 인증 불필요

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.vod` | series_nm 기준 에피소드 조회. 커버링 인덱스 `idx_vod_series_nm_cover` 활용 |

---

### 2-6. `GET /series/{series_nm}/progress` — 시청 진행 현황

**기능 개요**: 특정 시리즈의 에피소드별 시청 진행률 반환 (이어보기 버튼용)

**기본 기능**:
- episode_progress + vod JOIN
- `last_episode`, `last_completion_rate` (마지막 시청 에피소드)
- 전체 에피소드별 completion_rate, watched_at

**예외사항**:
- 시청 기록 없으면 빈 배열 (에러 아님)

**제약사항**:
- 인증 필수 (JWT)

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.episode_progress` | user_id_fk + series_nm 기준 |
| 업스트림 | `public.vod` | asset_nm 조회 |

---

### 2-7. `POST /series/{series_nm}/episodes/{asset_nm}/progress` — 진행률 기록

**기능 개요**: 에피소드 시청 진행률 기록 (UPSERT)

**기본 기능**:
- asset_nm → full_asset_id 변환 (vod 테이블 조회)
- episode_progress에 INSERT ... ON CONFLICT UPDATE
- 요청: `{ "completion_rate": 75 }`
- 응답: `{ "episode_title": "...", "completion_rate": 75, "watched_at": "..." }`

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `INVALID_COMPLETION_RATE` | 400 | 0~100 범위 밖 |
| `EPISODE_NOT_FOUND` | 404 | series_nm + asset_nm 조합 없음 |

**제약사항**:
- completion_rate: SMALLINT 0~100 정수
- 업데이트 주기: 재생 종료 시 1회 (Redis 실시간 수신 → 매일 자정 DB 반영 예정)

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.vod` | asset_nm → full_asset_id 매핑 |
| 다운스트림 | `public.episode_progress` | UPSERT |

---

### 2-8. `GET /series/{series_nm}/purchase-check` — 구매 여부 확인

**기능 개요**: 특정 시리즈의 구매 여부 + 대여 만료 확인

**기본 기능**:
- purchase_history에서 최신 구매 기록 조회
- `is_expired` 계산: permanent → false, rental → `expires_at > NOW()` 체크
- 미구매 시: `{ "purchased": false, ... }`

**제약사항**:
- 인증 필수

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.purchase_history` | user_id_fk + series_nm 기준 |

---

### 2-9. `GET /series/{series_nm}/purchase-options` — 구매 옵션

**기능 개요**: 시리즈의 구매 옵션 반환 (FOD 무료 분기)

**기본 기능**:
- FOD 시리즈 (`asset_prod='FOD'`): `{ "is_free": true, "options": [] }`
- 유료 시리즈: `{ "is_free": false, "options": [{ "option_type": "rental", "points": 490, "duration": "48h" }, { "option_type": "permanent", "points": 1490, "duration": null }] }`

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `SERIES_NOT_FOUND` | 404 | series_nm이 vod 테이블에 없음 |

**제약사항**:
- 인증 불필요
- FOD 시리즈는 구매 절차 없이 "1화 시청하기" UI 표시

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.vod` | asset_prod 확인 |

---

### 2-10. `POST /purchases` — 포인트 구매

**기능 개요**: 포인트 차감 + purchase_history + point_history 동시 INSERT 트랜잭션

**기본 기능**:
- 요청: `{ "series_nm": "...", "option_type": "rental", "points_used": 490 }`
- 포인트 잔액 확인 (point_history SUM 집계)
- DB 트랜잭션: purchase_history INSERT → point_history INSERT
- rental: `expires_at = NOW() + 48h`, permanent: `expires_at = NULL`
- 응답: `{ "purchase_id": 123, "remaining_points": 99510, "expires_at": "..." }`

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `INVALID_OPTION_TYPE` | 400 | rental/permanent 아님 |
| `INVALID_POINTS_AMOUNT` | 400 | points_used ≤ 0 |
| `INSUFFICIENT_POINTS` | 402 | 잔액 부족 |

**제약사항**:
- 포인트 잔액 = `SUM(CASE WHEN type='earn' THEN amount ELSE -amount END)`
- 음수 방지는 Frontend 팝업 + API 402로 대응 (DB CHECK 제약 없음)
- 인증 필수

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.point_history` | 잔액 집계 |
| 다운스트림 | `public.purchase_history` | 구매 기록 INSERT |
| 다운스트림 | `public.point_history` | 사용 내역 INSERT |

---

### 2-11. `POST /wishlist` — 찜 추가

**기능 개요**: 시리즈 찜 추가 (멱등 — 이미 존재 시 무시)

**기본 기능**:
- 요청: `{ "series_nm": "눈물의 여왕" }`
- `INSERT ... ON CONFLICT DO NOTHING`
- 응답: `{ "series_nm": "...", "created_at": "..." }`

**제약사항**:
- PK = (user_id_fk, series_nm)
- 중복 추가 시 에러 아닌 기존 데이터 반환

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 다운스트림 | `public.wishlist` | INSERT |

---

### 2-12. `DELETE /wishlist/{series_nm}` — 찜 해제

**기능 개요**: 찜 목록에서 시리즈 제거

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `WISHLIST_NOT_FOUND` | 404 | 찜 목록에 없는 시리즈 |

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 다운스트림 | `public.wishlist` | DELETE |

---

### 2-13. `GET /user/me/watching` — 시청 중 콘텐츠

**기능 개요**: 진행률 1~99%인 에피소드 (최신순, 기본 10개)

**기본 기능**:
- episode_progress WHERE completion_rate BETWEEN 1 AND 99
- vod JOIN으로 메타데이터 보강
- 응답 필드: `series_nm`, `episode_title`, `poster_url`, `completion_rate`, `watched_at`

**제약사항**:
- 완료(100%) 또는 미시작(0%) 제외

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.episode_progress` | 진행률 필터 |
| 업스트림 | `public.vod` | 메타데이터 JOIN |

---

### 2-14. `GET /user/me/profile` — 유저 프로필

**기능 개요**: 유저 표시명 + 포인트 잔액 반환

**기본 기능**:
- `user_name` = sha2_hash 앞 5자
- `point_balance` = point_history 실시간 집계
- 응답: `{ "user_name": "a1b2c", "point_balance": 100000 }`

**예외사항**:
| 에러 코드 | HTTP | 조건 |
|-----------|------|------|
| `PROFILE_NOT_FOUND` | 404 | 유저 없음 |

**제약사항**:
- 쿠폰 기능 제거 확정 (coupon_count 필드 없음)

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public."user"` | sha2_hash 존재 확인 |
| 업스트림 | `public.point_history` | 잔액 집계 |

---

### 2-15. `GET /user/me/points` — 포인트 잔액 + 내역

**기능 개요**: 포인트 잔액과 최근 적립/사용 내역 반환

**기본 기능**:
- balance: point_history SUM 집계
- history: 최근 N건 (기본 20, 최대 100)
- 각 내역: `type`(earn/use), `amount`, `description`, `created_at`

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.point_history` | 집계 + 내역 |

---

### 2-16. `GET /user/me/history` — 시청 내역

**기능 개요**: 에피소드 시청 내역 (episode_progress 기반, watch_history 미노출)

**기본 기능**:
- episode_progress 전체 (completion_rate 무관) 최신순
- 응답 필드: `series_nm`, `episode_title`, `poster_url`, `completion_rate`, `watched_at`

**제약사항**:
- `watch_history` raw 데이터는 ML 전용 — 유저에게 직접 노출하지 않음

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.episode_progress` | 시청 내역 |
| 업스트림 | `public.vod` | 메타데이터 JOIN |

---

### 2-17. `GET /user/me/purchases` — 구매 내역

**기능 개요**: 포인트 구매/대여 내역 반환

**기본 기능**:
- purchase_history 최신순
- 응답 필드: `series_nm`, `option_type`, `points_used`, `purchased_at`, `expires_at`

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.purchase_history` | 구매 내역 |

---

### 2-18. `GET /user/me/wishlist` — 찜 목록

**기능 개요**: 찜한 시리즈 목록 (최신순)

**기본 기능**:
- wishlist + vod 서브쿼리로 poster_url 보강
- 응답 필드: `series_nm`, `poster_url`, `created_at`

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `public.wishlist` | 찜 목록 |
| 업스트림 | `public.vod` | poster_url 서브쿼리 |

---

### 2-19. `GET /recommend/{user_id}` — 개인화 추천

**기능 개요**: CF_Engine/Vector_Search 결과 기반 개인화 추천 목록

**기본 기능**:
- vod_recommendation (user_id_fk 기준) + TTL 필터
- fallback: mv_vod_watch_stats (인기순)
- 응답 필드: `asset_id`, `title`, `genre`, `poster_url`, `score`, `rank`, `recommendation_type`

**제약사항**:
- tag_recommendation 기반 패턴 그룹핑 구현 예정 (DDL 반영 후)

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `serving.vod_recommendation` | 개인화 추천 (user_id_fk) |
| 업스트림 | `serving.mv_vod_watch_stats` | 인기 fallback |
| 업스트림 | `public.vod` | 메타데이터 JOIN |

---

### 2-20. `GET /similar/{asset_id}` — 유사 콘텐츠

**기능 개요**: 기준 VOD와 유사한 콘텐츠 목록 (콘텐츠 기반 추천)

**기본 기능**:
- vod_recommendation (`source_vod_id` 기준) + TTL 필터
- recommendation_type: VISUAL_SIMILARITY, CONTENT_BASED
- fallback: 동일 장르 VOD
- 응답 필드: `asset_id`, `title`, `genre`, `poster_url`, `score`, `rank`

**제약사항**:
- `source_vod_id` 사용 (user_id_fk 아님 — 2026-03-20 버그 수정 완료)

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `serving.vod_recommendation` | 콘텐츠 기반 추천 (source_vod_id) |
| 업스트림 | `public.vod` | 장르 fallback + 메타데이터 JOIN |

---

### 2-21. `WS /ad/popup` — 광고 팝업 (WebSocket) — 구현 예정

**기능 개요**: VOD 재생 중 사물인식 트리거 기반 광고 팝업 실시간 전송

**기본 기능**:

**타입 1: 지역광고 (`local_gov`)**
- 지역 사진 + 축제 이름 + 축제 일정 움직이는 팝업
- 유저 버튼 없음
- 10초 후 자동 최소화 → 파란색(다시 열기) / 빨간색(완전 제거) 버튼

**타입 2: 제철장터 (`seasonal_market`)**
- "채널 25번 제철장터에서 {상품명} 판매중" 메시지
- 버튼: 시청예약하기 / 종료하기
- 시청예약 → "시청예약되었습니다" 2초 후 자동 제거
- 종료 → 즉시 제거
- 10초 후 미응답 시 자동 최소화

**Client → Server 액션**:
- `reserve_watch`: 시청예약
- `dismiss`: 완전 제거
- `minimize`: 최소화
- `reopen`: 다시 열기

**의존성**:
| 방향 | 대상 | 용도 |
|------|------|------|
| 업스트림 | `serving.shopping_ad` | 트리거 포인트 + 광고 데이터 |
| 업스트림 | `public.tv_schedule` | 제철장터 방송 시간 |

---

## 3. DB 테이블 의존성 전체 맵

### 3-1. 업스트림 (읽기)

| 테이블 | 엔드포인트 |
|--------|-----------|
| `public.vod` | /vod, /home, /series/episodes, /similar, /user/watching, /user/history |
| `public."user"` | /auth/token, /user/me/profile |
| `public.episode_progress` | /series/progress, /user/watching, /user/history |
| `public.purchase_history` | /series/purchase-check, /user/purchases |
| `public.point_history` | /user/profile, /user/points, /purchases (잔액 확인) |
| `public.wishlist` | /user/wishlist |
| `serving.vod_recommendation` | /recommend, /similar |
| `serving.popular_recommendation` | /home/banner, /home/sections |
| `serving.shopping_ad` | /ad/popup (WebSocket) |

### 3-2. 다운스트림 (쓰기)

| 테이블 | 엔드포인트 |
|--------|-----------|
| `public.episode_progress` | POST /series/{id}/episodes/{id}/progress |
| `public.purchase_history` | POST /purchases |
| `public.point_history` | POST /purchases |
| `public.wishlist` | POST /wishlist, DELETE /wishlist/{id} |

---

## 4. 미구현 / 추후 반영 항목

| 항목 | 상태 | 대기 사유 |
|------|------|----------|
| `/recommend` 패턴 그룹핑 | DDL 대기 | `serving.tag_recommendation` 미반영 |
| `disp_rtm_min` 러닝타임 | DDL 대기 | `public.vod` 컬럼 추가 필요 |
| Redis 캐시 레이어 | 설계 필요 | completion_rate 실시간 → 매일 자정 DB 반영 |
| 에피소드 검색 (초성) | 구현 필요 | 출연진 초성검색 + 회차 검색 |
| 공통 에러 구조화 코드 | 구현 필요 | APIError 클래스 + exception handler |
| WebSocket `/ad/popup` | 구현 필요 | Shopping_Ad 연동 |

---

## 부록: Notion 페이지 작성 실무 가이드

### A. 페이지 구조 (팀원용 작업 지시 시 참고)

```
VOD 추천 시스템 (워크스페이스)
├── 기술 명세서
│   ├── API_Server (이 문서)
│   ├── Database_Design
│   ├── CF_Engine
│   ├── Vector_Search
│   ├── Object_Detection
│   ├── Shopping_Ad
│   └── Frontend
├── 협의 기록
│   ├── 프론트엔드 요구사항
│   └── 결정 사항 로그
└── 진행 현황
    └── 브랜치별 진척 대시보드
```

### B. 엔드포인트 페이지 작성 템플릿

각 엔드포인트 페이지는 아래 6개 섹션을 포함해야 합니다:

```
## {메서드} {경로} — {한글 기능명}

### 기능 개요
> 1~2문장으로 이 엔드포인트가 무엇을 하는지 설명

### 기본 기능
- 요청 형식 (Query param / Path param / Body)
- 처리 로직 (SQL, 비즈니스 룰)
- 응답 형식 (필드 목록)

### 예외사항
| 에러 코드 | HTTP 상태 | 발생 조건 | 사용자 메시지 |

### 제약사항
- 인증 필요 여부
- 데이터 제한 (범위, 타입)
- 성능 고려사항

### 업스트림 의존성
| 테이블 | 컬럼 | 용도 |

### 다운스트림 의존성
| 테이블 | 컬럼 | 용도 |
```

### C. Notion API 연동 시 주의사항

1. **페이지 생성**: `POST /v1/pages` — parent에 database_id 또는 page_id 지정
2. **블록 추가**: `PATCH /v1/blocks/{block_id}/children` — heading, table, callout 등
3. **테이블**: Notion 테이블은 `table` + `table_row` 블록 조합. Markdown 테이블 직접 삽입 불가
4. **코드 블록**: `code` 블록 타입으로 SQL/Python 삽입 가능
5. **토글**: 긴 섹션은 `toggle` 블록으로 접기 처리 권장
6. **이모지**: Notion 페이지 아이콘으로 엔드포인트 유형 구분 가능 (GET=📖, POST=✏️, DELETE=🗑️, WS=🔌)
