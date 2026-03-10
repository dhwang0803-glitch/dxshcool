커밋 전 보안 점검을 실행해줘. 아래 단계를 순서대로 수행하고 최종 결과를 보고해.

## 1. 점검 대상 파일 수집

```bash
# staged 파일 목록
git diff --cached --name-only

# staged 파일 중 .py 파일만
git diff --cached --name-only --diff-filter=ACM | grep '\.py$'
```

staged 파일이 없으면 아래 명령으로 마지막 커밋 파일 점검:
```bash
git diff HEAD~1 --name-only --diff-filter=ACM | grep '\.py$'
```

---

## 2. 보안 규칙 점검 (CLAUDE.md 기준)

각 점검은 Grep 도구를 사용해. 점검 대상은 1단계에서 수집한 파일들.

### CHECK-01 하드코딩 자격증명
패턴: `(API_KEY|PASSWORD|SECRET|TOKEN|api_key|password|secret|token)\s*=\s*["\'][^"\']{6,}["\']`

위반 예시:
```python
TMDB_API_KEY = "abcd1234..."   # ❌
DB_PASSWORD  = "mysecret"      # ❌
```

### CHECK-02 os.getenv() 실제 인프라 기본값
패턴: `os\.getenv\s*\([^)]+,\s*["\'][^"\']*["\']` 로 getenv 기본값 라인 추출 후
아래 실제 인프라 정보가 기본값에 들어있는지 확인:
- 실제 IP 주소 (예: `10.0.0.1`)
- 실제 DB명 (예: `prod_db`)
- 실제 사용자명 (예: `dbadmin`)
- 공개 표준값은 허용: `localhost`, `5432`, `postgres`, `""`, `"5432"`

### CHECK-03 env.get() 실제 인프라 기본값
패턴: `env\.get\s*\([^)]+,\s*["\'][^"\']+["\']`
CHECK-02와 동일한 기준으로 기본값 검사.

### CHECK-04 .env 파일 staged 여부
```bash
git diff --cached --name-only | grep -E '\.env$|\.env\.'
```
`.env` 파일이 staged되어 있으면 즉시 FAIL.

### CHECK-05 .gitignore 필수 항목 확인
```bash
cat .gitignore 2>/dev/null || cat VOD_Embedding/.gitignore 2>/dev/null
```
아래 항목이 포함되어 있는지 확인:
- `.env`
- `*.pem`, `*.key`
- `credentials.json`
- `.claude/settings.local.json`

### CHECK-06 하드코딩 경로 (개인 로컬 경로)
패턴: `C:/Users/[^"\']+` 또는 `C:\\Users\\[^"\']+`
코드 내 하드코딩된 개인 로컬 경로 탐지.
상수(DEFAULT_*, MODEL_PATH 등)로 분리되어 있고 CLI 인자로 덮어쓸 수 있으면 WARNING(허용), 함수 내부 직접 사용이면 FAIL.

---

## 3. 결과 보고

아래 형식으로 보고해:

```
=== 보안 감사 결과 ===
점검 파일: N개
점검 시각: YYYY-MM-DD HH:MM

CHECK-01 하드코딩 자격증명   : PASS / FAIL
CHECK-02 getenv 인프라 기본값 : PASS / FAIL
CHECK-03 env.get 인프라 기본값: PASS / FAIL
CHECK-04 .env staged 여부    : PASS / FAIL
CHECK-05 .gitignore 항목     : PASS / FAIL
CHECK-06 하드코딩 경로       : PASS / WARNING / FAIL

전체 결과: ✅ PASS (커밋 진행 가능) / ❌ FAIL (즉시 수정 필요)
```

FAIL 항목이 있으면:
- 위반 파일명과 라인 번호를 명시
- 수정 방법을 코드 예시로 제시
- 수정 완료 전까지 커밋하지 않는다

WARNING은 커밋 가능하나 사유를 설명해야 함.
