# 백엔드 추가 요청 사항

> 프론트엔드 연동을 위해 백엔드에 **추가/변경** 요청하는 항목.
> 협의완료 문서(`docs/프론트엔드_요구사항(협의완료).md`) 기준으로 미포함 사항만 기재.
> 작성일: 2026-03-21

| # | 항목 | 상태 | 구현일 |
|---|------|------|--------|
| 1 | 개인화 홈 섹션 (`GET /home/sections/{user_id}`) | ✅ 완료 | 2026-03-21 |
| 2 | 알림 시스템 (4개 엔드포인트 + notifications 테이블 + 트리거) | ✅ 완료 | 2026-03-21 |
| 3 | GNB 통합 검색 (`GET /vod/search?q={query}`) | ✅ 완료 | 2026-03-21 |

---

## 1. ✅ `GET /home/sections` → 개인화 버전으로 변경 요청

### 현재 구현 (협의완료 기준)

```
GET /home/sections
→ CT_CL 4종(영화/TV드라마/TV 연예·오락/TV애니메이션) × top 20 고정 반환
```

### 변경 요청

```
GET /home/sections/{user_id}
→ 사용자의 장르별 시청 비중을 분석해 개인화된 섹션 순서 + 미시청 장르 도전 섹션 반환
```

**응답 스펙:**
```json
{
  "sections": [
    {
      "genre": "범죄/스릴러",
      "view_ratio": 38,
      "vod_list": [
        { "series_nm": "...", "asset_nm": "...", "poster_url": "..." }
      ]
    },
    {
      "genre": "새로운 장르 도전",
      "view_ratio": 0,
      "vod_list": [...]
    }
  ]
}
```

**동작 기준:**
- `view_ratio` = 해당 장르 시청 횟수 / 전체 시청 횟수 × 100 (정수, `watch_history` 기반 계산)
- 섹션 순서: `view_ratio` 내림차순 정렬
- 마지막 섹션: 한 번도 시청하지 않은 장르 중 1개를 "새로운 장르 도전"으로 추가 (`view_ratio: 0`)
- 콘텐츠 소스: `serving.popular_recommendation` (장르별 인기순)
- 비회원/신규 유저(시청 이력 없음): 기존 CT_CL 4종 고정 응답으로 fallback

**소스 테이블:** `watch_history`, `serving.popular_recommendation`

---

## 2. ✅ 알림 시스템 신규 엔드포인트 + DB 테이블

GNB 알림 벨에 시청예약 외 **신규 에피소드 알림** 등 다양한 알림 유형 표시가 필요함.
현재 `watch_reservation`은 사용자가 직접 등록한 예약만 관리하므로 서버 발송 알림은 별도 테이블 필요.

### 신규 엔드포인트 (4개)

| 엔드포인트 | 설명 | 소스 테이블 |
|-----------|------|------------|
| `GET /user/me/notifications` | 알림 목록 (최신순, 전체) | `notifications` |
| `PATCH /user/me/notifications/{id}/read` | 알림 읽음 처리 | `notifications` |
| `DELETE /user/me/notifications/{id}` | 알림 삭제 | `notifications` |
| `POST /user/me/notifications/read-all` | 전체 읽음 처리 | `notifications` |

**`GET /user/me/notifications` 응답 스펙:**
```json
[
  {
    "id": 1,
    "type": "new_episode",
    "title": "선재 업고 튀어",
    "message": "새로운 에피소드가 등록되었습니다",
    "image_url": "string | null",
    "read": false,
    "created_at": "2026-03-21T10:00:00Z"
  },
  {
    "id": 2,
    "type": "reservation",
    "title": "제철장터",
    "message": "2시간 후에 시작합니다",
    "image_url": "string | null",
    "read": false,
    "created_at": "2026-03-21T09:00:00Z"
  }
]
```

> 알림 뱃지 카운트: `read=false` 개수를 프론트에서 계산.

### 신규 DB 테이블

```sql
CREATE TABLE public.notifications (
  id          SERIAL        PRIMARY KEY,
  user_id     VARCHAR(64)   NOT NULL,
  type        VARCHAR(32)   NOT NULL,  -- 'new_episode' | 'reservation' | 'system'
  title       VARCHAR(255)  NOT NULL,
  message     VARCHAR(512)  NOT NULL,
  image_url   TEXT,
  read        BOOLEAN       NOT NULL DEFAULT false,
  created_at  TIMESTAMPTZ   DEFAULT now()
);
CREATE INDEX idx_notifications_user ON public.notifications (user_id, created_at DESC);
```

**알림 생성 트리거 예시:**
- 새 에피소드 VOD INSERT → 해당 시리즈를 찜한 유저(`wishlist`)에게 `new_episode` 알림 자동 발송
- `watch_reservation` 알림 시각(`alert_at`) 도달 → `reservation` 알림 생성

---

## 3. ✅ GNB 통합 검색 신규 엔드포인트

GNB 검색창에서 제목·출연진·감독·장르를 통합 검색하는 기능을 추가했으나, 협의완료 문서에 해당 엔드포인트가 없음.
(협의완료의 "에피소드 검색"은 시리즈 상세 페이지 내부 검색으로 별개)

### 신규 엔드포인트

| 엔드포인트 | 설명 |
|-----------|------|
| `GET /vod/search?q={query}` | 제목·출연진·감독·장르 통합 검색, 최대 8건 반환 |

**응답 스펙:**
```json
[
  {
    "series_nm": "범죄도시4",
    "asset_nm": "범죄도시4",
    "genre": "범죄/액션",
    "ct_cl": "영화",
    "poster_url": "string"
  }
]
```

**검색 대상 컬럼:** `asset_nm`(제목), `cast_lead`(출연진), `director`(감독), `genre`(장르)
**소스 테이블:** `public.vod`

---

## 공통 사항

| 항목 | 내용 |
|------|------|
| 에러 응답 | 기존 형식 동일: `{"error": {"code": "...", "message": "한글 메시지"}}` |
| 인증 | 기존 JWT 방식 동일 (`Authorization: Bearer <token>`) |
