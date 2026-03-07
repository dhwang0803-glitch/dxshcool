# Claude Code 프로젝트 가이드라인

## 보안 규칙 (필수)

### 절대 하지 말 것
- `.env` 파일을 Read 도구로 읽지 말 것
- `.env` 파일 내용을 대화창에 출력하지 말 것
- DB 비밀번호, API 키 등 실제 자격증명 값을 응답 텍스트에 포함하지 말 것
- `settings.local.json`에 자격증명 값을 하드코딩하지 말 것

### DB 접속 명령어 작성 규칙
환경변수 참조 방식만 사용한다. 값을 직접 쓰지 않는다.

```bash
# 올바른 방식
set -a && source .env && set +a
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME

# 잘못된 방식 (절대 금지)
PGPASSWORD=실제비밀번호 psql -h 실제IP ...
```

### 사용자에게 안내할 것
- 자격증명이 필요한 경우: 사용자가 직접 터미널에서 입력하도록 안내
- .env 내용 공유 요청 시: 보안상 채팅에 붙여넣기 하지 말도록 안내
- 새 자격증명 설정 시: `.env.example`만 제공하고 실제 값은 사용자가 직접 입력

---

## 프로젝트 개요

- **프로젝트**: VOD 추천 시스템 PostgreSQL 데이터베이스
- **브랜치**: Database_Design (작업 브랜치), main (통합 브랜치)
- **DB**: PostgreSQL 15.4 on Docker (VPC)
- **접속 정보**: `.env` 파일 (Git 제외, 팀 내 별도 공유)

## 커밋 금지 파일

- `.env` — DB 접속 정보
- `.claude/settings.local.json` — Claude Code 로컬 설정 (자격증명 포함 가능)
- `data/` — CSV 원본 데이터 (대용량)
