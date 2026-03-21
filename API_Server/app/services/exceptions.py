"""공통 API 예외 — error_message_policy.md 기반 표준화.

모든 에러는 팩토리 함수로 정의하여 raise 시마다 새 인스턴스 생성.
동시 요청 환경에서 __traceback__ 공유 문제를 방지한다.
"""


class APIError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code


# ── 400 Bad Request ──────────────────────────────────────────

def INVALID_OPTION_TYPE() -> APIError:
    return APIError("INVALID_OPTION_TYPE", "구매 유형은 rental 또는 permanent만 선택할 수 있습니다", 400)

def INVALID_POINTS_AMOUNT() -> APIError:
    return APIError("INVALID_POINTS_AMOUNT", "포인트는 0보다 큰 값이어야 합니다", 400)

def INVALID_COMPLETION_RATE() -> APIError:
    return APIError("INVALID_COMPLETION_RATE", "시청 진행률은 0~100 범위여야 합니다", 400)


# ── 401 Unauthorized ─────────────────────────────────────────

def INVALID_TOKEN() -> APIError:
    return APIError("INVALID_TOKEN", "인증 정보가 유효하지 않습니다", 401)

def TOKEN_DECODE_FAILED() -> APIError:
    return APIError("TOKEN_DECODE_FAILED", "인증 토큰을 확인할 수 없습니다", 401)


# ── 402 Payment Required ─────────────────────────────────────

def INSUFFICIENT_POINTS(balance: int, required: int) -> APIError:
    return APIError(
        "INSUFFICIENT_POINTS",
        f"포인트가 부족합니다 (잔액: {balance:,}P, 필요: {required:,}P)",
        402,
    )


# ── 404 Not Found ────────────────────────────────────────────

def USER_NOT_FOUND() -> APIError:
    return APIError("USER_NOT_FOUND", "등록되지 않은 사용자입니다", 404)

def PROFILE_NOT_FOUND() -> APIError:
    return APIError("PROFILE_NOT_FOUND", "사용자 정보를 찾을 수 없습니다", 404)

def SERIES_NOT_FOUND() -> APIError:
    return APIError("SERIES_NOT_FOUND", "해당 시리즈를 찾을 수 없습니다", 404)

def EPISODE_NOT_FOUND() -> APIError:
    return APIError("EPISODE_NOT_FOUND", "해당 에피소드를 찾을 수 없습니다", 404)

def VOD_NOT_FOUND() -> APIError:
    return APIError("VOD_NOT_FOUND", "해당 콘텐츠를 찾을 수 없습니다", 404)

def SIMILAR_NOT_FOUND() -> APIError:
    return APIError("SIMILAR_NOT_FOUND", "유사한 콘텐츠를 찾을 수 없습니다", 404)

def WISHLIST_NOT_FOUND() -> APIError:
    return APIError("WISHLIST_NOT_FOUND", "찜 목록에 없는 시리즈입니다", 404)


# ── 500 Internal Server Error ─────────────────────────────────

def INTERNAL_ERROR() -> APIError:
    return APIError("INTERNAL_ERROR", "일시적인 오류가 발생했습니다. 잠시 후 다시 시도해주세요", 500)

def DB_CONNECTION_FAILED() -> APIError:
    return APIError("DB_CONNECTION_FAILED", "서비스에 일시적인 문제가 있습니다", 500)
