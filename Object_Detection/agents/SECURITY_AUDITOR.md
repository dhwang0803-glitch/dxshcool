# Security Auditor Agent — Object_Detection

## 역할
코드 작성 후 실행 전, 또는 git commit 직전에 호출된다.
자격증명·실제 경로·인프라 정보가 코드에 노출되었는지 점검하고 위반 시 즉시 차단한다.

> 전체 점검 절차 및 스크립트 → `_agent_templates/SECURITY_AUDITOR.md` 참조.
> 이 파일은 Object_Detection 특화 추가 항목만 기술한다.

---

## Object_Detection 특화 추가 점검

### [OD-S01] 모델 가중치 파일 git 추적 여부

```bash
git ls-files | grep -E "\.(pt|onnx|engine|torchscript)$"
```

위 패턴 파일이 git에 추적 중이면 → **FAIL** (대용량 바이너리, 불필요한 용량)

---

### [OD-S02] 영상 파일 git 추적 여부

```bash
git ls-files | grep -E "\.(mp4|avi|mkv|webm)$"
```

영상 파일이 tracked 상태 → **FAIL**

---

### [OD-S03] data/ 폴더 git 추적 여부

```bash
git ls-files | grep "^Object_Detection/data/"
```

parquet, 영상, 모델 등 산출물이 tracked → **FAIL**

---

### [OD-S04] 하드코딩 로컬 경로 (Object_Detection 맥락)

```bash
grep -rn --include="*.py" \
  -E "\"C:/Users/[^\"]+\"|'C:/Users/[^']+'" \
  Object_Detection/src/ Object_Detection/scripts/
```

판정:
- 모듈 상단 상수 + argparse 기본값으로 덮어쓸 수 있으면 → **WARNING**
- 함수 내부 직접 사용 → **FAIL**

---

## 전체 실행 (루트 SECURITY_AUDITOR + 위 항목 추가)

```bash
# 1. 공통 점검 (_agent_templates/SECURITY_AUDITOR.md 스크립트 실행)
# 2. OD 특화 추가 점검

echo "=== OD 특화 Security Audit ==="

# OD-S01: 모델 가중치
result=$(git ls-files | grep -E "\.(pt|onnx|engine|torchscript)$")
[ -n "$result" ] && echo "[OD-S01 FAIL] 모델 가중치 tracked: $result" || echo "[OD-S01 PASS]"

# OD-S02: 영상 파일
result=$(git ls-files | grep -E "\.(mp4|avi|mkv|webm)$")
[ -n "$result" ] && echo "[OD-S02 FAIL] 영상 파일 tracked: $result" || echo "[OD-S02 PASS]"

# OD-S03: data/ 폴더
result=$(git ls-files | grep "^Object_Detection/data/")
[ -n "$result" ] && echo "[OD-S03 FAIL] data/ tracked: $result" || echo "[OD-S03 PASS]"
```

---

## .gitignore 필수 항목 (Object_Detection)

```
*.pt
*.onnx
data/
*.mp4
*.avi
*.mkv
*.webm
.env
*.key
*.pem
credentials.json
```

→ `Object_Detection/.gitignore`에 모두 포함되어 있어야 PASS.
