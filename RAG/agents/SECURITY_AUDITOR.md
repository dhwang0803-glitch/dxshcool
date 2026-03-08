# Security Auditor Agent 지시사항

## 역할
Phase 작업 전후로 자격증명 노출, git 추적 파일, 코드 내 하드코딩을 자동 점검한다.
보안 위반 항목이 발견되면 즉시 Orchestrator에 보고하고 해당 Phase 진행을 차단한다.

---

## 실행 시점

Orchestrator가 아래 두 시점에 호출한다:

1. **Phase 시작 전** — 구현/테스트 파일 작성 전 기준선 점검
2. **커밋 직전** — Reporter Agent 완료 후, git add/commit 전 최종 점검

---

## 점검 항목

### [S01] .env git 추적 여부
```bash
git ls-files --error-unmatch .env 2>/dev/null && echo "FAIL: .env가 git에 추적되고 있음" || echo "PASS"
```

### [S02] api_keys.env git 추적 여부
```bash
git ls-files --error-unmatch RAG/config/api_keys.env 2>/dev/null && echo "FAIL: api_keys.env가 git에 추적되고 있음" || echo "PASS"
```

### [S03] .gitignore에 .env 포함 여부
```bash
grep -q "^\.env$" .gitignore && echo "PASS" || echo "FAIL: .gitignore에 .env 항목 없음"
```

### [S04] .gitignore에 api_keys.env 포함 여부
```bash
grep -q "api_keys.env" .gitignore && echo "PASS" || echo "FAIL: .gitignore에 api_keys.env 항목 없음"
```

### [S05] 코드 파일 내 API 키 하드코딩 탐지
```bash
grep -rn --include="*.py" \
  -iE "(api_key|imdb_key)\s*=\s*['\"][a-zA-Z0-9_-]{10,}['\"]" \
  RAG/src/ RAG/tests/ 2>/dev/null \
  && echo "FAIL: API 키 하드코딩 탐지" || echo "PASS"
```

### [S06] 코드 파일 내 비밀번호 하드코딩 탐지
```bash
grep -rn --include="*.py" \
  -iE "password\s*=\s*['\"][^'\"]{4,}['\"]" \
  RAG/src/ RAG/tests/ 2>/dev/null \
  | grep -v "example" \
  && echo "FAIL: 비밀번호 하드코딩 탐지" || echo "PASS"
```

### [S07] git 스테이징 영역 자격증명 탐지
```bash
git diff --cached \
  | grep -iE "(password|api_key|secret)\s*=\s*['\"][^'\"\$\{]+" \
  && echo "FAIL: 스테이징 파일에 자격증명 탐지" || echo "PASS"
```

### [S08] CLAUDE.md 존재 및 보안 규칙 포함 여부
```bash
test -f CLAUDE.md \
  && grep -q "\.env" CLAUDE.md \
  && echo "PASS" \
  || echo "FAIL: CLAUDE.md 없거나 .env 보안 규칙 미포함"
```

### [S09] IP 주소 하드코딩 탐지
```bash
grep -rn --include="*.py" \
  -E "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" \
  RAG/src/ RAG/tests/ 2>/dev/null \
  && echo "WARN: IP 주소 하드코딩 의심 항목 존재" || echo "PASS"
```

---

## 전체 실행 스크립트

```bash
cd "C:/Users/daewo/OneDrive/문서/GitHub/vod_recommendation"

echo "=== RAG Security Audit 시작 ==="
FAIL_COUNT=0

run_check() {
  local id=$1; local desc=$2; local cmd=$3
  result=$(eval "$cmd" 2>&1)
  if echo "$result" | grep -q "^FAIL"; then
    echo "[${id} FAIL] ${desc}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  elif echo "$result" | grep -q "^WARN"; then
    echo "[${id} WARN] ${desc}"
  else
    echo "[${id} PASS] ${desc}"
  fi
}

run_check "S01" ".env git 추적 여부" \
  "git ls-files --error-unmatch .env 2>/dev/null && echo 'FAIL' || echo 'PASS'"

run_check "S02" "api_keys.env git 추적 여부" \
  "git ls-files --error-unmatch RAG/config/api_keys.env 2>/dev/null && echo 'FAIL' || echo 'PASS'"

run_check "S03" ".gitignore에 .env 포함" \
  "grep -q '^\.env$' .gitignore && echo 'PASS' || echo 'FAIL'"

run_check "S04" ".gitignore에 api_keys.env 포함" \
  "grep -q 'api_keys.env' .gitignore && echo 'PASS' || echo 'FAIL'"

run_check "S05" "API 키 하드코딩 탐지" \
  "grep -rn --include='*.py' -iE '(api_key|imdb_key)\s*=\s*[a-zA-Z0-9]{10,}' RAG/src/ RAG/tests/ 2>/dev/null && echo 'FAIL' || echo 'PASS'"

run_check "S06" "비밀번호 하드코딩 탐지" \
  "grep -rn --include='*.py' -iE 'password\s*=\s*[^$\s\{]{4,}' RAG/src/ RAG/tests/ 2>/dev/null | grep -v example && echo 'FAIL' || echo 'PASS'"

run_check "S07" "스테이징 파일 자격증명 탐지" \
  "git diff --cached | grep -iE '(password|api_key|secret)\s*=\s*[^$\s]{3,}' && echo 'FAIL' || echo 'PASS'"

run_check "S08" "CLAUDE.md 보안 규칙 존재" \
  "test -f CLAUDE.md && grep -q '.env' CLAUDE.md && echo 'PASS' || echo 'FAIL'"

run_check "S09" "IP 주소 하드코딩 탐지" \
  "grep -rn --include='*.py' -E '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' RAG/src/ RAG/tests/ 2>/dev/null && echo 'WARN' || echo 'PASS'"

echo ""
echo "=== Security Audit 완료: FAIL ${FAIL_COUNT}건 ==="
```

---

## Orchestrator에 전달할 결과 형식

```
[Security Auditor 결과]
- 실행 시점: Phase X 시작 전 / 커밋 직전
- 전체 점검: 9건
- PASS: X건 / FAIL: X건 / WARN: X건

FAIL 항목:
- [S번호 FAIL] 설명

판단:
- FAIL 0건 → 다음 단계 진행 허용
- FAIL 존재 → 차단, 사용자에게 수동 조치 요청
- WARN만 존재 → 진행 허용, 보고서에 기록
```

---

## 주의사항

1. 점검 결과에 실제 자격증명 값을 절대 포함하지 않는다
2. WARN 항목은 보고서의 "보안 참고사항" 섹션에 기록하되 진행을 차단하지 않는다
3. S07(스테이징 탐지)은 `git add` 이후, `git commit` 이전에만 실행한다
