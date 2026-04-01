# 보안 가이드

이 저장소의 모든 기여자가 준수해야 하는 보안 규칙입니다.
**코드 수정 및 커밋 전 반드시 확인하세요.**

---

## 1. 자격증명 하드코딩 금지

API 키, 비밀번호, 토큰을 코드에 직접 작성하지 않습니다.

```python
# ❌ 절대 금지
TMDB_API_KEY = "abcd1234efgh5678"
DB_PASSWORD  = "mysecretpassword"

# ✅ 올바른 방식 — 환경변수에서 읽기
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DB_PASSWORD  = os.getenv("DB_PASSWORD")
```

---

## 2. os.getenv() 기본값에 실제 인프라 정보 금지

`os.getenv()` 두 번째 인자(기본값)에 실제 서버 IP, DB명, 사용자명을 넣지 않습니다.

```python
# ❌ 절대 금지 — 기본값에 실제 인프라 정보 노출
host   = os.getenv("DB_HOST", "10.0.0.1")
dbname = os.getenv("DB_NAME", "prod_db")
user   = os.getenv("DB_USER",  "dbadmin")

# ✅ 올바른 방식 — 기본값 없이 (또는 공개 표준값만 허용)
host   = os.getenv("DB_HOST")
dbname = os.getenv("DB_NAME")
user   = os.getenv("DB_USER")
port   = int(os.getenv("DB_PORT", "5432"))  # 표준 포트는 허용
```

---

## 3. .env 파일 관리

### 절대 커밋하지 않을 파일
- `.env` (DB 접속 정보, API 키 포함)
- `*.pem`, `*.key` (인증서/키 파일)
- `credentials.json`
- `.claude/settings.local.json`

이 파일들은 `.gitignore`에 등록되어 있습니다. 실수로 staged되었다면:
```bash
git rm --cached .env
```

### .env 파일 사용 방법
프로젝트 루트의 `.env.example`을 복사해서 사용합니다:
```bash
cp .env.example .env
# .env 파일에 실제 값 입력 (절대 커밋하지 말 것)
```

---

## 4. 임베딩 출력 파일 (팀원 협업)

팀원이 생성한 `embeddings_*.parquet` 파일은 DB 자격증명을 포함하지 않지만,
**공용 저장소에 커밋하지 않습니다.** 파일 전달은 별도 채널(공유 드라이브 등)을 사용하세요.

```bash
# .gitignore에 이미 등록되어 있어야 함
data/
*.parquet
*.pkl
```

---

## 5. 커밋 전 점검

PR 생성 시 `/PR-report` 스킬이 아래 보안 점검을 자동 수행합니다:

```bash
# 하드코딩 자격증명 스캔
git diff | grep -E "(password|secret|api_key|token|host)\s*=\s*['\"][^'\"]{4,}"

# os.getenv 기본값에 실제 인프라 정보 스캔
git diff | grep -E "os\.getenv\(.+,\s*['\"]"

# staged 파일에 .env 포함 여부
git diff --cached --name-only | grep '\.env'
```

수동 점검 시에도 위 명령어를 사용하세요.

---

## 6. 위반 발견 시

1. 커밋을 즉시 중단
2. 해당 자격증명을 즉시 교체 (이미 노출된 경우)
3. git history에서 제거: `git filter-branch` 또는 `git-filter-repo`
4. 프로젝트 관리자에게 알림

> 실수로 커밋된 자격증명은 git history에서 완전히 삭제해야 합니다.
> `.gitignore`에 추가하는 것만으로는 기존 history에서 제거되지 않습니다.
