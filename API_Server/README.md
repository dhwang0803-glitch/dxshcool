# API_Server

VOD 추천 시스템 FastAPI 백엔드.
CF_Engine·Vector_Search·Shopping_Ad의 결과를 단일 REST API로 통합하여 Frontend에 제공한다.

---

## 엔드포인트

| 메서드 | 경로 | 설명 | 인증 |
|--------|------|------|------|
| GET | `/vod/{asset_id}` | VOD 상세 메타데이터 | 불필요 |
| GET | `/recommend/{user_id}` | 개인화 추천 목록 | JWT 필요 |
| GET | `/similar/{asset_id}` | 유사 콘텐츠 목록 | 불필요 |
| POST | `/auth/token` | JWT 발급 | 불필요 |
| WS | `/ad/popup` | 실시간 광고 트리거 | JWT 필요 (예정) |

---

## 실행 방법

```bash
# 1. 환경변수 설정 (.env 파일 — 조장에게 수령)
cp config/.env.example .env
# .env에 실제 값 입력

# 2. 패키지 설치
pip install fastapi uvicorn asyncpg python-jose[cryptography]

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
└── docs/plans/          ← PLAN_00~05 설계 문서
```

---

## 주의사항

- VPC `max_connections = 100` 제한 → asyncpg pool `max_size=10` 고정
- Gold 레이어(`serving.*`) 에서만 읽기 — 벡터 연산 수행 금지
- `.env` 파일 절대 커밋 금지

---

상세 설계 → `docs/plans/PLAN_00_MASTER.md`
