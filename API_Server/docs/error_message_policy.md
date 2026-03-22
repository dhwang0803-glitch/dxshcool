# API 에러 메시지 정책

> 작성일: 2026-03-20
> 전체 엔드포인트 에러 시나리오 정리 + 코드/메시지 표준화

---

## 공통 에러 응답 형식

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "사용자에게 표시할 한글 메시지"
  }
}
```

| 필드 | 설명 |
|------|------|
| `code` | 영문 대문자 스네이크케이스 — Frontend에서 분기 처리용 |
| `message` | 한글 사용자 안내 메시지 — UI에 직접 표시 가능 |

---

## HTTP 상태 코드별 에러 정의

### 400 Bad Request — 입력값 검증 실패

| 에러 코드 | 메시지 | 발생 엔드포인트 | 트리거 조건 |
|-----------|--------|----------------|------------|
| `INVALID_OPTION_TYPE` | 구매 유형은 rental 또는 permanent만 선택할 수 있습니다 | `POST /purchases` | `option_type`이 rental/permanent 아님 |
| `INVALID_POINTS_AMOUNT` | 포인트는 0보다 큰 값이어야 합니다 | `POST /purchases` | `points_used <= 0` |
| `INVALID_COMPLETION_RATE` | 시청 진행률은 0~100 범위여야 합니다 | `POST /series/{id}/episodes/{id}/progress` | `completion_rate < 0` 또는 `> 100` |

### 401 Unauthorized — 인증 실패

| 에러 코드 | 메시지 | 발생 엔드포인트 | 트리거 조건 |
|-----------|--------|----------------|------------|
| `INVALID_TOKEN` | 인증 정보가 유효하지 않습니다 | 인증 필요 전체 | JWT payload에 `sub` 없음 |
| `TOKEN_DECODE_FAILED` | 인증 토큰을 확인할 수 없습니다 | 인증 필요 전체 | JWT 디코딩 실패 (변조/잘못된 형식) |

### 402 Payment Required — 포인트 부족

| 에러 코드 | 메시지 | 발생 엔드포인트 | 트리거 조건 |
|-----------|--------|----------------|------------|
| `INSUFFICIENT_POINTS` | 포인트가 부족합니다 (잔액: {balance}P, 필요: {required}P) | `POST /purchases` | 포인트 잔액 < 구매 금액 |

### 404 Not Found — 리소스 없음

| 에러 코드 | 메시지 | 발생 엔드포인트 | 트리거 조건 |
|-----------|--------|----------------|------------|
| `USER_NOT_FOUND` | 등록되지 않은 사용자입니다 | `POST /auth/token` | sha2_hash가 user 테이블에 없음 |
| `PROFILE_NOT_FOUND` | 사용자 정보를 찾을 수 없습니다 | `GET /user/me/profile` | 인증된 사용자가 user 테이블에 없음 |
| `SERIES_NOT_FOUND` | 해당 시리즈를 찾을 수 없습니다 | `GET /series/{id}/episodes`, `GET /series/{id}/purchase-options` | series_nm이 vod 테이블에 없음 |
| `EPISODE_NOT_FOUND` | 해당 에피소드를 찾을 수 없습니다 | `POST /series/{id}/episodes/{id}/progress` | series_nm + asset_nm 조합이 없음 |
| `VOD_NOT_FOUND` | 해당 콘텐츠를 찾을 수 없습니다 | `GET /vod/{asset_id}` | full_asset_id가 vod 테이블에 없음 |
| `SIMILAR_NOT_FOUND` | 유사한 콘텐츠를 찾을 수 없습니다 | `GET /similar/{asset_id}` | 유사 콘텐츠 없음 (추천 + 장르 fallback 모두) |
| `WISHLIST_NOT_FOUND` | 찜 목록에 없는 시리즈입니다 | `DELETE /wishlist/{series_nm}` | 해당 찜 항목 없음 |

### 500 Internal Server Error — 서버 내부 오류

| 에러 코드 | 메시지 | 발생 조건 |
|-----------|--------|----------|
| `INTERNAL_ERROR` | 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요 | DB 연결 실패, 예상치 못한 예외 |
| `DB_CONNECTION_FAILED` | 서비스에 일시적인 문제가 있습니다 | 커넥션 풀 고갈/DB 응답 없음 |

---

## 담당자 결정 필요 항목

> 아래 항목은 에러 코드/메시지를 담당자가 직접 확정해야 합니다.

| # | 시나리오 | 현재 상태 | 결정 필요 |
|---|---------|----------|----------|
| 1 | 대여 만료된 콘텐츠 재생 시도 | 미구현 | 에러? 자동 구매 페이지 이동? |
| 2 | 이미 구매한 시리즈 재구매 시도 | 미구현 | 에러 반환? 무시? |
| 3 | 동일 시리즈 찜 중복 추가 | `ON CONFLICT DO NOTHING` (성공 반환) | 현행 유지? 별도 메시지? |
| 4 | WebSocket 연결 끊김 시 광고 상태 | 미구현 | 재연결 시 광고 복원? 무시? |

---

## 적용 방식

현재 FastAPI 기본 에러 형식 `{"detail": "..."}` → 위 구조화 형식으로 전환 필요.

**구현 방안**: `app/services/exceptions.py`에 커스텀 예외 클래스 정의 + `app/main.py`에 전역 exception handler 등록

```python
# 예시 구조
class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code

# main.py
@app.exception_handler(APIError)
async def api_error_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
```
