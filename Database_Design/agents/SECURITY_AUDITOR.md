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

### [S02] settings.local.json git 추적 여부
```bash
git ls-files --error-unmatch .claude/settings.local.json 2>/dev/null && echo "FAIL: settings.local.json이 git에 추적되고 있음" || echo "PASS"
```

### [S03] .gitignore에 .env 포함 여부
```bash
grep -q "^\.env$" .gitignore && echo "PASS" || echo "FAIL: .gitignore에 .env 항목 없음"
```

### [S04] .gitignore에 settings.local.json 포함 여부
```bash
grep -q "settings.local.json" .gitignore && echo "PASS" || echo "FAIL: .gitignore에 settings.local.json 항목 없음"
```

### [S05] 코드 파일 내 IP 주소 하드코딩 탐지
```bash
# .env, .gitignore, docs/, plans/ 제외하고 IP 패턴 탐색
grep -rn --include="*.py" --include="*.sql" --include="*.md" \
  -E "\b([0-9]{1,3}\.){3}[0-9]{1,3}\b" \
  --exclude-dir=".git" \
  Database_Design/ \
  | grep -v "plans/" | grep -v "reports/" | grep -v "agents/" \
  && echo "WARN: IP 주소 하드코딩 의심 항목 존재" || echo "PASS"
```

### [S06] 코드 파일 내 비밀번호 패턴 하드코딩 탐지
```bash
# 따옴표로 감싼 실제 값이 있는 경우만 탐지 (변수 대입은 제외)
# 예: password="secret" → FAIL / password=db_password → PASS (변수)
grep -rn --include="*.py" --include="*.sql" --include="*.json" \
  -iE "(password|passwd)\s*=\s*['\"][^'\"]{4,}['\"]" \
  --exclude-dir=".git" \
  . \
  | grep -v "example" \
  && echo "FAIL: 비밀번호 하드코딩 탐지" || echo "PASS"
```

### [S07] git 스테이징 영역 자격증명 탐지
```bash
# 커밋 직전 점검: 스테이징된 파일에 자격증명 패턴이 있는지 확인
git diff --cached \
  | grep -iE "(password|passwd|secret|api_key)\s*=\s*['\"][^'\"\$\{]+" \
  && echo "FAIL: 스테이징 파일에 자격증명 탐지" || echo "PASS"
```

### [S08] CLAUDE.md 존재 및 보안 규칙 포함 여부
```bash
test -f CLAUDE.md \
  && grep -q "\.env" CLAUDE.md \
  && echo "PASS" \
  || echo "FAIL: CLAUDE.md 없거나 .env 보안 규칙 미포함"
```

### [S09] Bash 명령어 내 자격증명 직접 참조 탐지 (agent 파일)
```bash
grep -rn --include="*.md" \
  -E "PGPASSWORD=[^$\s]{3,}" \
  Database_Design/agents/ \
  && echo "FAIL: agent 파일에 PGPASSWORD 하드코딩 탐지" || echo "PASS"
```

---

## 전체 실행 스크립트

```bash
cd /c/Users/user/Documents/GitHub/vod_recommendation

echo "=== Security Audit 시작 ==="
FAIL_COUNT=0

run_check() {
  local id=$1
  local desc=$2
  local cmd=$3
  result=$(eval "$cmd" 2>&1)
  if echo "$result" | grep -q "^FAIL"; then
    echo "[${id} FAIL] ${desc}"
    echo "  → ${result}"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  elif echo "$result" | grep -q "^WARN"; then
    echo "[${id} WARN] ${desc}"
    echo "  → ${result}"
  else
    echo "[${id} PASS] ${desc}"
  fi
}

run_check "S01" ".env git 추적 여부" \
  "git ls-files --error-unmatch .env 2>/dev/null && echo 'FAIL' || echo 'PASS'"

run_check "S02" "settings.local.json git 추적 여부" \
  "git ls-files --error-unmatch .claude/settings.local.json 2>/dev/null && echo 'FAIL' || echo 'PASS'"

run_check "S03" ".gitignore에 .env 포함 여부" \
  "grep -q '^\.env$' .gitignore && echo 'PASS' || echo 'FAIL: .gitignore에 .env 항목 없음'"

run_check "S04" ".gitignore에 settings.local.json 포함 여부" \
  "grep -q 'settings.local.json' .gitignore && echo 'PASS' || echo 'FAIL'"

run_check "S05" "코드 파일 내 IP 하드코딩 탐지" \
  "grep -rn --include='*.py' --include='*.sql' -E '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' Database_Design/migration/ Database_Design/tests/ 2>/dev/null && echo 'WARN' || echo 'PASS'"

run_check "S06" "코드 파일 내 비밀번호 하드코딩 탐지" \
  "grep -rn --include='*.py' --include='*.sql' --include='*.json' -iE 'password\s*=\s*[^$\s\{]{3,}' --exclude-dir='.git' . 2>/dev/null | grep -v '.env' | grep -v 'example' && echo 'FAIL' || echo 'PASS'"

run_check "S07" "스테이징 파일 자격증명 탐지" \
  "git diff --cached | grep -iE '(password|secret|api_key)\s*=\s*[^$\s]{3,}' && echo 'FAIL' || echo 'PASS'"

run_check "S08" "CLAUDE.md 보안 규칙 존재 여부" \
  "test -f CLAUDE.md && grep -q '.env' CLAUDE.md && echo 'PASS' || echo 'FAIL'"

run_check "S09" "agent 파일 PGPASSWORD 하드코딩 탐지" \
  "grep -rn --include='*.md' -E 'PGPASSWORD=[^\$\s]{3,}' Database_Design/agents/ && echo 'FAIL' || echo 'PASS'"

echo ""
echo "=== Security Audit 완료: FAIL ${FAIL_COUNT}건 ==="
```

---

## Orchestrator에 전달할 결과 형식

```
[Security Auditor 결과]
- 실행 시점: Phase X 시작 전 / 커밋 직전
- 전체 점검: 9건
- PASS: X건
- FAIL: X건
- WARN: X건

FAIL 항목:
- [S번호 FAIL] 설명

판단:
- FAIL 0건 → 다음 단계 진행 허용
- FAIL 존재 → 해당 Phase 또는 커밋 차단, 사용자에게 수동 조치 요청
- WARN만 존재 → 진행 허용, 보고서에 기록
```

---

## 주의사항

1. 점검 결과를 출력할 때 실제 자격증명 값을 절대 포함하지 않는다
2. `grep` 결과에 실제 비밀번호 값이 나오면 `***` 로 마스킹 후 보고한다
3. S07(스테이징 탐지)은 `git add` 이후, `git commit` 이전에만 실행한다
4. WARN 항목은 보고서의 "보안 참고사항" 섹션에 기록하되 진행을 차단하지 않는다
