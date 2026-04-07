# API_Server

VOD 추천 시스템 FastAPI 백엔드.
CF_Engine·Vector_Search·Shopping_Ad의 결과를 단일 REST API로 통합하여 Frontend에 제공한다.

---

## 엔드포인트

### 인증

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/auth/token` | JWT 발급 (셋톱박스 자동 로그인, 만료 없음) | 불필요 |

### 홈

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/home/banner` | 히어로 배너 (popular top 5 + hybrid top 10) | 선택적 |
| GET | `/home/sections` | CT_CL 4종 인기 섹션 | 불필요 |
| GET | `/home/sections/{user_id}` | 개인화 섹션 (태그+cold+벡터+TOP10) | JWT 필요 |

### 추천/검색

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/recommend/{user_id}` | 개인화 추천 (top 10 + 태그 패턴 + 벡터 유사도) | JWT 필요 |
| GET | `/similar/{asset_id}` | 유사 콘텐츠 | 불필요 |
| GET | `/vod/search?q={query}` | GNB 통합 검색 (제목/출연진/감독/장르) | 불필요 |

### VOD/시리즈

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/vod/{asset_id}` | VOD 상세 메타데이터 | 불필요 |
| GET | `/series/{id}/episodes` | 에피소드 목록 | 불필요 |
| GET | `/series/{id}/progress` | 시청 진행 현황 | JWT 필요 |
| POST | `/series/{id}/episodes/{id}/progress` | 진행률 heartbeat | JWT 필요 |
| GET | `/series/{id}/purchase-check` | 구매 여부 확인 | JWT 필요 |
| GET | `/series/{id}/purchase-options` | 구매 옵션 | 불필요 |

### 마이페이지

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/user/me/watching` | 시청 중 콘텐츠 | JWT 필요 |
| GET | `/user/me/profile` | 프로필 | JWT 필요 |
| GET | `/user/me/points` | 포인트 잔액 + 내역 | JWT 필요 |
| GET | `/user/me/history` | 시청 내역 | JWT 필요 |
| GET | `/user/me/purchases` | 구매 내역 | JWT 필요 |
| GET | `/user/me/wishlist` | 찜 목록 | JWT 필요 |

### 구매/찜/예약

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| POST | `/purchases` | 포인트 구매 트랜잭션 | JWT 필요 |
| POST | `/wishlist` | 찜 추가 | JWT 필요 |
| DELETE | `/wishlist/{series_nm}` | 찜 해제 | JWT 필요 |
| POST | `/reservations` | 시청예약 등록 | JWT 필요 |
| GET | `/reservations` | 시청예약 목록 | JWT 필요 |
| DELETE | `/reservations/{id}` | 시청예약 취소 | JWT 필요 |

### 알림

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/user/me/notifications` | 알림 목록 | JWT 필요 |
| PATCH | `/user/me/notifications/{id}/read` | 알림 읽음 처리 | JWT 필요 |
| POST | `/user/me/notifications/read-all` | 전체 읽음 처리 | JWT 필요 |
| DELETE | `/user/me/notifications/{id}` | 알림 삭제 | JWT 필요 |

### 광고

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| WS | `/ad/popup` | 실시간 광고 팝업 (WebSocket) | JWT 필요 |

---

## 실행 방법

```bash
# 1. 환경변수 설정 (.env 파일 — 조장에게 수령)
cp config/.env.example .env
# .env에 실제 값 입력

# 2. 패키지 설치
pip install -r requirements.txt

# 3. 개발 서버 실행
set -a && source .env && set +a
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 4. API 문서 확인
# http://localhost:8000/docs
```

---

## 폴더 구조

```
API_Server/
├── app/
│   ├── main.py          ← FastAPI 진입점
│   ├── routers/         ← 엔드포인트별 라우터
│   ├── services/        ← DB 쿼리 등 비즈니스 로직
│   └── models/          ← Pydantic 요청/응답 스키마
├── tests/               ← pytest (httpx AsyncClient)
├── config/              ← settings.yaml, .env.example
└── docs/                ← 연동 가이드, 엔드포인트 스펙
```

---

## 배포

| 환경 | 서비스명 | 브랜치 |
|------|---------|--------|
| 개발 | `vod-api-dev` | `main` |
| 운영 | `vod-api` | `release` (main FF-only 머지) |

상세 → `docs/DEPLOY_PLAN.md`

---

## 주의사항

- VPC `max_connections = 100` 제한 → asyncpg pool `max_size=10` 고정
- Gold 레이어(`serving.*`)에서 추천 결과 읽기, `public` 스키마에 사용자 활동 기록
- `.env` 파일 절대 커밋 금지
- 실시간 갱신: PG LISTEN/NOTIFY + 인메모리 버퍼(60초 batch flush)
