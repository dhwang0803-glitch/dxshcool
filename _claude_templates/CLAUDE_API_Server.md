# API_Server — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**FastAPI 백엔드** — CF_Engine, Vector_Search, Shopping_Ad의 결과를
단일 REST API로 통합하여 Frontend에 제공한다.

## 파일 위치 규칙 (MANDATORY)

```
API_Server/
├── app/
│   ├── routers/    ← 엔드포인트별 라우터 (직접 실행 X)
│   ├── services/   ← 비즈니스 로직 (직접 실행 X)
│   ├── models/     ← Pydantic 요청/응답 스키마 (직접 실행 X)
│   └── main.py     ← FastAPI 앱 진입점
├── tests/          ← pytest (httpx TestClient)
└── config/         ← 환경별 설정 yaml
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 라우터 (`recommend.py`, `search.py` 등) | `app/routers/` |
| 비즈니스 로직 (DB 쿼리, 결과 조합) | `app/services/` |
| Pydantic 스키마 (`RecommendResponse` 등) | `app/models/` |
| FastAPI 앱 (`app = FastAPI()`) | `app/main.py` |
| pytest | `tests/` |
| 환경 설정 | `config/` |

**`API_Server/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
import psycopg2           # DB 연결
from jose import jwt      # JWT 인증
import uvicorn
```

## 엔드포인트 설계

| 메서드 | 경로 | 설명 | 소스 |
|--------|------|------|------|
| GET | `/recommend/{user_id}` | 개인화 추천 | CF_Engine |
| GET | `/similar/{asset_id}` | 유사 콘텐츠 | Vector_Search |
| WS/SSE | `/ad/popup` | 실시간 광고 트리거 | Shopping_Ad |
| GET | `/vod/{asset_id}` | VOD 상세 메타데이터 | DB |
| POST | `/auth/token` | JWT 발급 | 자체 |

## 실행

```bash
# 개발 서버
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 인터페이스

- **업스트림**: `CF_Engine` (추천), `Vector_Search` (유사도), `Shopping_Ad` (광고), `Database_Design` (메타데이터)
- **다운스트림**: `Frontend` — REST API 및 WebSocket 소비
