# Git 브랜치 협업 완전 가이드
## VSCode에서 Git 설정부터 협업까지 모든 것

---

## 📋 목차

1. [VSCode에서 Git 저장소 설정](#vscode에서-git-저장소-설정)
2. [프로젝트 구조 이해](#프로젝트-구조-이해)
3. [Branch 개별 폴더에 파일 저장 및 Push](#branch-개별-폴더에-파일-저장-및-push)
4. [Main 공통 폴더에 파일 저장 및 Push](#main-공통-폴더에-파일-저장-및-push)
5. [기존 Git Repository Pull 하기](#기존-git-repository-pull-하기)
6. [Daily Workflow](#daily-workflow)
7. [자주 하는 실수와 해결방법](#자주-하는-실수와-해결방법)

---

## VSCode에서 Git 저장소 설정

### 1단계: VSCode 설치 및 Git 설치 확인

```powershell
# PowerShell에서 Git 버전 확인
git --version

# 출력: git version 2.x.x
# (버전이 나오면 설치됨, 아니면 https://git-scm.com에서 설치)
```

### 2단계: VSCode 확장 프로그램 설치

```
VSCode 왼쪽 아이콘 바에서:
1. Extensions (네모 아이콘) 클릭
2. 검색: "Git Graph"
3. 설치 (원하는 Git 시각화 도구)

권장 확장:
- Git Graph (브랜치 시각화)
- GitLens (Git 정보 표시)
- GitHub Pull Requests and Issues
```

### 3단계: 프로젝트 폴더 열기

```
Method 1: VSCode에서 폴더 열기
1. VSCode 열기
2. File → Open Folder
3. 프로젝트 폴더 선택 (예: vod_recommendation)
4. 폴더 신뢰 (Trust the authors)

Method 2: PowerShell에서 열기
cd C:\Users\user\Documents\GitHub\vod_recommendation
code .
```

### 4단계: Git 저장소 초기화 (첫 번째 팀원만)

```powershell
# 기존 저장소가 있으면 이 단계 스킵!

# 새로운 프로젝트인 경우만:
git init
git remote add origin https://github.com/username/vod_recommendation.git
git branch -M main
git push -u origin main
```

### 5단계: VSCode에서 Git 상태 확인

```
VSCode 왼쪽 아이콘 바:
- Source Control (분기 아이콘) 클릭
- 현재 브랜치 표시
- 변경된 파일 목록 표시
```

✅ **완료: VSCode Git 설정**

---

## 프로젝트 구조 이해

### 전체 폴더 구조

```
vod_recommendation/
│
├── main 브랜치 (기본 분기점)
│   ├── .claude/                    ← ⭐ 공통 폴더 (모든 팀이 사용)
│   │   ├── instructions.md
│   │   ├── agents/
│   │   ├── commands/
│   │   ├── plans/
│   │   └── skills/
│   ├── Database_Design/.gitkeep    ← 빈 폴더 (main에만)
│   ├── RAG/.gitkeep
│   ├── feature/
│   │   ├── api-backend/.gitkeep
│   │   ├── ml-engine/.gitkeep
│   │   └── video-pipeline/.gitkeep
│   ├── src/                        ← 향후 공통 코드
│   ├── tests/
│   ├── docs/
│   ├── .gitignore
│   ├── LICENSE
│   └── README.md
│
├── Database_Design 브랜치
│   └── Database_Design/            ← ⭐ 전용 폴더
│       ├── .claude/claude.md
│       ├── schema/
│       ├── migration/
│       └── skills/
│
├── RAG 브랜치
│   └── RAG/                        ← ⭐ 전용 폴더
│       ├── .claude/claude.md
│       ├── src/
│       └── data/
│
├── feature/api-backend 브랜치
│   └── feature/api-backend/        ← ⭐ 전용 폴더
│       ├── .claude/claude.md
│       └── src/
│
├── feature/ml-engine 브랜치
│   └── feature/ml-engine/          ← ⭐ 전용 폴더
│       ├── .claude/claude.md
│       └── src/
│
└── feature/video-pipeline 브랜치
    └── feature/video-pipeline/     ← ⭐ 전용 폴더
        ├── .claude/claude.md
        └── src/
```

### 🔑 핵심 개념

```
공통 폴더 (main에서만 수정):
├── .claude/
├── src/
├── tests/
├── docs/
├── .gitignore
└── 기타 설정 파일

전용 폴더 (해당 브랜치에서만 수정):
├── Database_Design/
├── RAG/
├── feature/api-backend/
├── feature/ml-engine/
└── feature/video-pipeline/
```

---

## Branch 개별 폴더에 파일 저장 및 Push

### 시나리오: Database_Design 팀이 schema 파일 추가

#### Step 1: 올바른 브랜치에 있는지 확인

```powershell
# PowerShell에서
git branch

# 출력:
#   RAG
# * Database_Design     ← 별표(*)가 현재 브랜치
#   main
```

**또는 VSCode에서:**

```
VSCode 하단 왼쪽 모서리에 "Database_Design" 표시 확인
클릭하면 브랜치 전환 가능
```

#### Step 2: 파일 생성/수정

```powershell
# 파일 생성 예시
mkdir -p Database_Design\schema

# SQL 파일 생성
@"
-- Users Table
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Videos Table
CREATE TABLE videos (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    duration INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"@ | Out-File -Encoding UTF8 Database_Design\schema\01_initial_schema.sql
```

**또는 VSCode에서:**

```
1. Explorer (왼쪽 상단 아이콘)
2. Database_Design 폴더 마우스 우클릭
3. New File → schema/01_initial_schema.sql
4. 내용 입력 후 Ctrl+S 저장
```

#### Step 3: VSCode에서 변경사항 확인

```
1. Source Control (분기 아이콘) 클릭
2. Changes 섹션에 파일 표시됨
3. 파일명 옆의 "+" 아이콘 클릭하거나
   전체 폴더 "+" 클릭으로 스테이징
```

#### Step 4: PowerShell에서 변경사항 확인 및 추가

```powershell
# 변경사항 확인
git status

# 출력:
# On branch Database_Design
# Untracked files:
#   (use "git add <file>..." to include in what will be committed)
#         Database_Design/schema/01_initial_schema.sql
#
# nothing added to commit but untracked files present (use "git add" to track)

# 파일 추가 (Database_Design 폴더만!)
git add Database_Design\schema\

# 또는 전체 추가
git add Database_Design\

# 확인
git status

# 출력:
# On branch Database_Design
# Changes to be committed:
#   new file:   Database_Design/schema/01_initial_schema.sql
```

**또는 VSCode에서:**

```
1. Source Control에서 파일 옆 "+" 클릭
2. 파일이 Staged Changes로 이동
```

#### Step 5: 커밋

```powershell
# PowerShell에서
git commit -m "feat: Add initial database schema for users and videos"

# 확인
git log --oneline -3
```

**또는 VSCode에서:**

```
1. Source Control에서 메시지 입력 칸 클릭
2. "feat: Add initial database schema..." 입력
3. Ctrl+Enter 또는 체크 아이콘 클릭으로 커밋
```

#### Step 6: Push (브랜치로!)

```powershell
# Database_Design 브랜치로 푸시
git push origin Database_Design

# 출력:
# Enumerating objects: 5, done.
# Counting objects: 100% (5/5), done.
# Delta compression using up to 8 threads
# Compressing objects: 100% (3/3), done.
# Writing objects: 100% (3/3), 1.23 KiB | 1.23 MiB/s, done.
# Total 3 (delta 0), reused 0 (delta 0), pack-reused 0
# To https://github.com/username/vod_recommendation.git
#    abc1234..def5678  Database_Design -> Database_Design
```

#### Step 7: 확인

```powershell
# 로컬 상태 확인
git status

# 출력:
# On branch Database_Design
# nothing to commit, working tree clean ✅
```

✅ **완료: 브랜치 파일 Push**

---

## Main 공통 폴더에 파일 저장 및 Push

### 시나리오: 팀 리더가 .claude/ 폴더에 새로운 가이드 문서 추가

#### Step 1: main 브랜치로 전환

```powershell
# PowerShell에서
git switch main

# 확인
git branch

# 출력:
#   Database_Design
#   RAG
# * main              ← 현재 여기
```

**또는 VSCode에서:**

```
1. 하단 왼쪽 "Database_Design" 클릭
2. 드롭다운에서 "main" 선택
```

#### Step 2: 파일 생성/수정

```powershell
# 파일 생성 예시
@"
# API 개발 가이드

## 엔드포인트 설계 원칙

1. RESTful 설계
   - GET: 조회
   - POST: 생성
   - PUT: 수정
   - DELETE: 삭제

2. 응답 형식
   - 성공: {status: "success", data: {...}}
   - 실패: {status: "error", message: "..."}

3. 에러 코드
   - 400: Bad Request
   - 401: Unauthorized
   - 404: Not Found
   - 500: Server Error
"@ | Out-File -Encoding UTF8 .claude\API_DEVELOPMENT_GUIDE.md
```

**또는 VSCode에서:**

```
1. Explorer에서 .claude 폴더 마우스 우클릭
2. New File → API_DEVELOPMENT_GUIDE.md
3. 내용 입력 후 저장
```

#### Step 3: 변경사항 확인 및 추가

```powershell
# 변경사항 확인
git status

# 출력:
# On branch main
# Untracked files:
#   (use "git add <file>..." to include in what will be committed)
#         .claude/API_DEVELOPMENT_GUIDE.md

# .claude 폴더 파일만 추가
git add .claude\

# 또는 전체 추가
git add .
```

#### Step 4: 커밋

```powershell
# 커밋 메시지 작성 (main에서의 변경이므로 명확하게)
git commit -m "docs: Add API development guidelines to .claude"

# 확인
git log --oneline -3
```

#### Step 5: Push (main으로!)

```powershell
# main 브랜치로 푸시 (항상 main!)
git push origin main

# 출력:
# To https://github.com/username/vod_recommendation.git
#    xyz9876..abc1234  main -> main
```

#### Step 6: 다른 팀들이 변경사항 받기

**⚠️ 중요: main에서 파일이 수정되었으므로, 다른 모든 브랜치가 업데이트 받아야 함**

```powershell
# Database_Design 팀
git switch Database_Design
git pull origin main

# RAG 팀
git switch RAG
git pull origin main

# API 팀
git switch feature/api-backend
git pull origin main

# 모든 브랜치가 같은 .claude/ 파일을 가짐 ✅
```

✅ **완료: Main 파일 Push 및 모든 브랜치 동기화**

---

## 기존 Git Repository Pull 하기

### 새로운 팀원이 처음 프로젝트에 참여

#### Step 1: GitHub에서 저장소 주소 복사

```
GitHub 저장소 페이지 (예: https://github.com/username/vod_recommendation)
1. 초록색 "Code" 버튼 클릭
2. HTTPS 탭에서 주소 복사
   예: https://github.com/username/vod_recommendation.git
```

#### Step 2: PowerShell에서 저장소 Clone

```powershell
# 프로젝트 폴더가 들어갈 위치로 이동
cd C:\Users\user\Documents\GitHub

# 저장소 Clone (전체 내용 다운로드)
git clone https://github.com/username/vod_recommendation.git

# 폴더로 이동
cd vod_recommendation

# 확인
ls -Force
```

#### Step 3: 모든 브랜치 확인

```powershell
# 로컬 브랜치만 보임
git branch

# 출력:
# * main

# 원격 브랜치도 보려면
git branch -a

# 출력:
# * main
#   remotes/origin/Database_Design
#   remotes/origin/RAG
#   remotes/origin/feature/api-backend
#   remotes/origin/feature/ml-engine
#   remotes/origin/feature/video-pipeline
```

#### Step 4: 자신이 작업할 브랜치 선택 및 전환

```powershell
# 예시: Database_Design 팀에 참여하는 새로운 팀원

# 방법 1: 원격 브랜치에서 로컬 브랜치 생성
git switch Database_Design
# 또는
git checkout -b Database_Design origin/Database_Design

# 확인
git branch

# 출력:
# * Database_Design
#   main
```

#### Step 5: 최신 상태로 동기화

```powershell
# 현재 브랜치의 최신 내용 받기
git pull origin Database_Design

# 또는 모든 브랜치 동기화
git fetch origin
```

#### Step 6: VSCode에서 확인

```
1. VSCode 열기 (폴더 선택)
2. Source Control 클릭
3. 현재 브랜치와 변경사항 확인
4. File Explorer에서 폴더 구조 확인
```

#### Step 7: 첫 번째 변경 전에 본인의 브랜치 동기화

```powershell
# 최신 변경사항 받기
git pull origin Database_Design

# 또는 main의 공통 폴더 업데이트 받기
git fetch origin main
git merge origin/main --no-edit

# 상태 확인
git status

# 출력:
# On branch Database_Design
# nothing to commit, working tree clean ✅
```

✅ **완료: 새로운 팀원 온보딩**

---

## Daily Workflow

### 매일 아침 (출근 후)

#### 1. 변경사항 확인

```powershell
# 현재 브랜치 확인
git branch

# 최신 상태 가져오기
git fetch origin

# 상태 확인
git status
```

#### 2. 필요하면 동기화

```powershell
# 현재 브랜치 업데이트
git pull origin Database_Design

# main의 공통 폴더 업데이트 받기 (선택)
git fetch origin main
git merge origin/main --no-edit
```

### 작업 중 (진행 중)

#### 1. 파일 수정

```powershell
# VSCode에서 파일 수정 또는

# PowerShell에서 파일 생성
@"
파일 내용
"@ | Out-File -Encoding UTF8 Database_Design\schema\users.sql
```

#### 2. 수시로 커밋

```powershell
# 작은 단위로 자주 커밋
git add Database_Design\schema\users.sql
git commit -m "feat: Add users table schema"

# 또는
git add Database_Design\
git commit -m "refactor: Update migration folder structure"
```

### 퇴근 전 (작업 마무리)

#### 1. 모든 변경사항 Push

```powershell
# 현재 상태 확인
git status

# 변경사항 있으면 커밋
git commit -m "feat: Complete user table schema"

# Push
git push origin Database_Design

# 확인
git status
# 출력: nothing to commit, working tree clean ✅
```

#### 2. 팀원들이 받을 수 있도록 준비

```powershell
# 커밋이 푸시되었는지 확인
git log --oneline -3

# GitHub 웹사이트에서도 확인
# https://github.com/username/vod_recommendation/tree/Database_Design
```

### Weekly (주간)

#### 1. main의 공통 폴더 업데이트 받기

```powershell
# 모든 팀원
git fetch origin main
git merge origin/main

# 충돌 없으면 완료
git status
# 출력: nothing to commit, working tree clean ✅
```

#### 2. 전체 브랜치 상태 확인

```powershell
# 모든 브랜치의 최신 커밋 확인
git log --oneline --all --graph -20

# 또는 VSCode의 Git Graph 확장 사용
```

---

## 자주 하는 실수와 해결방법

### 실수 1: 브랜치를 확인하지 않고 작업

```powershell
# ❌ 실수
git status
# "On branch main" (실수로 main에서 작업)

# ✅ 해결
git switch Database_Design

# 작업 중에 했으면
git add .
git commit -m "temporary commit"

# main으로 리셋
git reset --soft HEAD~1

# Database_Design으로 전환 후 다시 커밋
git switch Database_Design
git add .
git commit -m "feat: Add database schema"
```

### 실수 2: 잘못된 폴더 수정

```powershell
# ❌ 실수: Database_Design에서 .claude/ 수정
git switch Database_Design
# .claude/skills/에 파일 추가 (공통 폴더인데!)

# ✅ 해결
git reset --hard HEAD

# main으로 이동해서 다시 수정
git switch main
git add .claude\skills\
git commit -m "feat: Add skills files"
git push origin main

# 다른 팀원들이 받기
git switch Database_Design
git pull origin main
```

### 실수 3: Push 전에 Pull 안 함

```powershell
# ❌ 문제: 팀원이 이미 같은 파일 수정해서 Push했음
git push origin Database_Design
# error: failed to push some refs to origin

# ✅ 해결
git pull origin Database_Design

# 충돌이 있으면 해결
# (VSCode에서 "Current" vs "Incoming" 선택)

# 다시 Push
git push origin Database_Design
```

### 실수 4: main으로 실수로 Push

```powershell
# ❌ 문제: Database_Design 파일을 main으로 푸시
git push origin main
# Database_Design의 파일들이 main에도 반영됨 (문제!)

# ✅ 해결 (GitHub 관리자만 가능)
# GitHub 웹사이트에서 최근 커밋 revert
# 또는 문제 발생시 팀 리더에게 보고
```

### 실수 5: 로컬과 원격이 다른 상태

```powershell
# ❌ 문제: GitHub에는 새 파일이 있는데 로컬에 없음
git status
# "Your branch is behind 'origin/Database_Design' by 1 commit"

# ✅ 해결
git pull origin Database_Design

# 또는
git fetch origin
git merge origin/Database_Design

# 확인
git status
# 새 파일 로컬에도 있음 ✅
```

---

## 팀 규칙 (팀 리더가 정해야 함)

```
1. 커밋 메시지 규칙:
   feat: 새 기능
   fix: 버그 수정
   docs: 문서 변경
   refactor: 코드 리팩토링
   chore: 설정 변경

   예: "feat: Add users table schema"

2. 푸시 규칙:
   - 1일 2회 이상 푸시 (중간중간)
   - 퇴근 전 반드시 푸시
   - Pull Request 필요 여부 결정

3. 동기화 규칙:
   - 매일 아침 git pull 실행
   - main 변경사항 주 1회 이상 받기
   - 주 1회 팀 회의에서 전체 동기화

4. 충돌 해결:
   - 충돌 시 같은 파일 수정 팀원과 협의
   - 수동으로 해결 후 Pull Request
   - 3명 이상 검토 후 Merge
```

---

## 체크리스트

### 새로운 팀원 온보딩

```
[ ] Git 설치
[ ] VSCode 설치 및 확장 (Git Graph, GitLens)
[ ] GitHub 저장소 주소 받기
[ ] git clone으로 저장소 받기
[ ] 할당된 브랜치로 전환 (git switch)
[ ] git pull로 최신 상태 받기
[ ] VSCode에서 폴더 구조 확인
[ ] 첫 번째 작업 전에 git status 확인
```

### 매일 체크

```
[ ] git branch로 올바른 브랜치 확인
[ ] git status로 변경사항 확인
[ ] git add로 파일 스테이징
[ ] git commit으로 메시지 작성
[ ] git push로 푸시 (올바른 브랜치로!)
[ ] 퇴근 전 git status = "clean" 확인
```

### 주간 체크

```
[ ] git fetch origin main으로 최신 공통 폴더 확인
[ ] git merge origin/main으로 동기화
[ ] 팀원들과 충돌 확인 및 해결
[ ] 전체 git log 확인
```

---

## 긴급 상황 연락

```
문제 발생시:
1. 멈추고 git status 실행
2. 스크린샷 찍기
3. 팀 리더에게 보고
4. "git reset --hard HEAD"로 마지막 커밋으로 돌아가기

절대 하면 안 될 것:
❌ git push --force (다른 팀원의 작업 삭제됨)
❌ git rebase main (역사 변경)
❌ 여러 브랜치에 동시 푸시
```

---

## 참고 자료

### 자주 사용하는 명령어

```powershell
# 현재 상태 확인
git status

# 브랜치 확인/전환
git branch
git switch Database_Design

# 변경사항 받기
git pull origin Database_Design
git fetch origin

# 파일 추가/커밋/푸시
git add Database_Design\
git commit -m "message"
git push origin Database_Design

# 히스토리 확인
git log --oneline -10
git log --all --graph --oneline

# 변경사항 취소
git restore <file>        # 파일 복구
git reset --soft HEAD~1   # 마지막 커밋 취소 (파일 유지)
git reset --hard HEAD~1   # 마지막 커밋 취소 (파일 삭제)
```

### 추천 Learning Resources

```
- GitHub Docs: https://docs.github.com
- Atlassian Git Tutorial: https://www.atlassian.com/git/tutorials
- Visual Git Reference: http://marklodato.github.io/visual-git-guide/
- Interactive Git Learning: https://learngitbranching.js.org/
```

---

## 마지막 조언

```
Git은 협업의 생명입니다.

1. 자주 커밋하세요 (하루에 5-10번)
2. 명확한 메시지를 쓰세요
3. 푸시 전에 항상 git status 확인
4. 모르면 먼저 팀 리더에게 물어보세요
5. "git reset --hard" 전에 팀 리더에게 보고하세요

Happy Collaborating! 🚀
```


내컴퓨터 지역저장소 (local repository)
보냄:push
받음:pull

다른사람 컴퓨터 (local repository)


