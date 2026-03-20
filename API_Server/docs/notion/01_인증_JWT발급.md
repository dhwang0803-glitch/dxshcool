# POST /auth/token — JWT 발급

## 기능 개요

셋톱박스에 등록된 유저 ID(sha2_hash)로 만료 없는 JWT 토큰을 발급한다.
IPTV 셋톱박스 전원 ON 시 자동으로 호출되며, 별도의 비밀번호/OAuth 없이 인증이 완료된다.

## 기본 기능

**요청**:
```json
POST /auth/token
{ "user_id": "a1b2c3d4e5..." }
```

**처리 로직**:
1. `public."user"` 테이블에서 `sha2_hash` 존재 확인
2. 존재하면 JWT 발급 (payload: `{ "sub": "sha2_hash값" }`, 만료 없음)
3. HS256 알고리즘, `JWT_SECRET_KEY` 환경변수 사용

**응답**:
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}
```

## 예외사항

| 에러 코드 | HTTP | 조건 | 메시지 |
|-----------|------|------|--------|
| `USER_NOT_FOUND` | 404 | sha2_hash가 user 테이블에 없음 | 등록되지 않은 사용자입니다 |
| `INVALID_TOKEN` | 401 | JWT payload에 sub 없음 | 인증 정보가 유효하지 않습니다 |
| `TOKEN_DECODE_FAILED` | 401 | JWT 디코딩 실패 (변조) | 인증 토큰을 확인할 수 없습니다 |

## 제약사항

- `JWT_SECRET_KEY` 환경변수 필수 (미설정 시 서버 기동 실패)
- 비밀번호, OAuth, refresh token 없음 — sha2_hash만으로 인증
- 토큰 만료 없음 (셋톱박스 전원 = 인증 세션)
- 모든 인증 필요 엔드포인트는 `Authorization: Bearer {token}` 헤더 필수

## 업스트림 의존성

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public."user"` | `sha2_hash` | VARCHAR | PK 존재 확인 |

## 다운스트림 의존성

| 대상 | 용도 |
|------|------|
| 전체 인증 필요 엔드포인트 | `get_current_user` Depends로 Bearer 토큰 검증 |
