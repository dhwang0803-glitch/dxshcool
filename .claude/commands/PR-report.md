PR 작성 전 사전 점검 및 PR 본문을 자동으로 생성해줘.

## 1. 현재 브랜치 및 베이스 브랜치 확인

```bash
git branch --show-current
git log --oneline -5
```

현재 브랜치명과 베이스 브랜치(main 또는 개발 브랜치)를 확인해줘.

## 2. PR 사전 점검 — base 브랜치 최신화

아래 절차를 순서대로 실행해줘.

```bash
# 1) 원격 최신 상태 가져오기
git fetch origin

# 2) base 브랜치(main)와 현재 브랜치 간 diverge 여부 확인
git log HEAD..origin/main --oneline
git log origin/main..HEAD --oneline
```

- `origin/main`에 내 브랜치에 없는 커밋이 있으면 → **pull 먼저 수행**
- 충돌(conflict) 발생 시 → 사용자에게 충돌 파일 목록을 알리고 중단. 충돌 해결 후 재실행 요청.
- diverge 없으면 → 다음 단계로 진행

```bash
# 3) diverge가 있는 경우에만 실행
git pull origin main
```

## 3. 변경사항 분석

```bash
# 베이스 대비 변경된 파일 목록
git diff --name-status origin/main...HEAD

# 커밋 히스토리
git log origin/main..HEAD --oneline
```

위 결과를 바탕으로 아래 항목을 분석해줘:
- 변경된 파일 수 및 목록
- 추가/수정/삭제 구분
- 각 커밋의 주요 내용 요약

## 4. 보안 사전 점검

변경된 파일을 대상으로 아래 패턴을 스캔해줘.

```bash
# 하드코딩된 자격증명 탐지
git diff origin/main...HEAD | grep -E "(password|secret|api_key|token|host)\s*=\s*['\"][^'\"]{4,}"

# os.getenv 기본값에 실제 인프라 정보 탐지
git diff origin/main...HEAD | grep -E "os\.getenv\(.+,\s*['\"]"
```

- 탐지된 항목이 있으면 → **커밋 중단, 즉시 수정 요청**
- 이상 없으면 → "보안 점검 통과" 보고 후 계속 진행

## 5. PR 본문 자동 생성

위 분석 결과를 바탕으로 아래 형식으로 PR 본문을 작성하고, `gh pr create` 명령어를 실행해줘.

PR 본문 형식:

```
## 변경사항 요약
<!-- 무엇을 왜 변경했는지 간결하게 기술 (bullet 3개 이내) -->

## 사후 영향 평가
<!-- 이 변경이 다른 브랜치/모듈/팀원 작업에 미치는 영향 -->
| 영향 범위 | 내용 | 조치 필요 여부 |
|-----------|------|---------------|
| 업스트림 의존성 | ... | Yes / No |
| 다운스트림 의존성 | ... | Yes / No |
| DB 스키마 변경 | ... | Yes / No |
| API 인터페이스 변경 | ... | Yes / No |

## 보안 평가
- [ ] 하드코딩된 자격증명 없음
- [ ] os.getenv() 기본값에 실제 인프라 정보 없음
- [ ] .env, *.pem, credentials.json이 .gitignore에 포함됨
- [ ] 외부 입력값 검증 적용됨 (해당 시)

## 테스트 체크리스트
- [ ] 로컬 실행 확인
- [ ] 주요 변경 함수 단위 테스트
- [ ] 관련 팀원에게 리뷰 요청

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

`gh pr create` 명령어로 PR을 생성할 때 위 본문을 사용하고, title은 마지막 커밋 메시지 또는 변경사항 요약을 기반으로 자동 생성해줘.
