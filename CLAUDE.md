# VOD Recommendation — Claude Code 프로젝트 규칙

모든 브랜치 공통 지침. 브랜치별 CLAUDE.md가 있으면 이 파일과 함께 적용된다.

---

## 브랜치 구조

| 브랜치 | 역할 |
|---|---|
| `main` | 공통 설정, `.claude/commands/` |
| `VOD_Embedding` | CLIP 임베딩 파이프라인 (`VOD_Embedding/`) |
| `Database_Design` | DB 스키마 설계 |
| `RAG` | 메타데이터 결측치 자동수집 파이프라인 (`RAG/`) |

---

## 🔒 보안 규칙 (MANDATORY — 모든 브랜치 적용)

**파일 수정/생성 또는 git commit 전 반드시 검증한다.**

### 1. 하드코딩된 자격증명 금지
```python
# ❌ 절대 금지
TMDB_API_KEY = "abcd1234..."
DB_PASSWORD  = "mysecret"

# ✅ 올바른 방식
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
DB_PASSWORD  = os.getenv("DB_PASSWORD")
```

### 2. os.getenv() 기본값에 실제 인프라 정보 금지
```python
# ❌ 절대 금지 — 실제 서버 IP·DB명·사용자명 노출
host=os.getenv("DB_HOST", "10.0.0.1")
dbname=os.getenv("DB_NAME", "prod_db")
user=os.getenv("DB_USER", "dbadmin")

# ✅ 올바른 방식
host=os.getenv("DB_HOST")
dbname=os.getenv("DB_NAME")
user=os.getenv("DB_USER")
port=int(os.getenv("DB_PORT", "5432"))  # 공개 표준 포트는 허용
```

### 3. .env 파일 직접 읽기 금지
- `.env` 파일을 Read 도구로 읽지 않는다
- `.env` 내용을 대화창·로그에 출력하지 않는다
- DB 비밀번호·API 키 실제 값을 응답 텍스트에 포함하지 않는다

### 4. DB 접속 명령어 작성 규칙
```bash
# ✅ 올바른 방식
set -a && source .env && set +a
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME

# ❌ 절대 금지
PGPASSWORD=실제비밀번호 psql -h 실제IP ...
```

### 5. .gitignore 확인
커밋 전 아래 파일이 .gitignore에 포함되어 있는지 확인:
- `.env`
- `*.pem`, `*.key`, `credentials.json`
- `.claude/settings.local.json`

### 6. Pre-commit 점검 절차
```
파일 수정 시 →
  Grep: "os\.getenv\(.*,\s*[\"']" 패턴 스캔 →
    기본값에 실제 인프라 정보 있으면 즉시 제거 →
      commit 전 보안 점검 결과 명시적으로 보고
```

**위반 시**: 커밋 중단, 즉시 수정 후 재커밋
