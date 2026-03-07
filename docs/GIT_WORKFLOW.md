# Git 기본 워크플로우

---

## Git 저장소의 3가지 공간

```
[로컬 작업 폴더]  →  [스테이징 영역]  →  [로컬 저장소]  →  [원격 저장소 GitHub]
   파일 수정         git add            git commit         git push
```

---

## 각 명령어가 하는 일

### git add — 스테이징

"이 파일의 변경사항을 다음 커밋에 포함하겠다"고 **예약**하는 작업

```bash
git add COLLABORATION.md        # 특정 파일만
git add Database_Design/plans/  # 폴더 전체
```

- 파일을 수정해도 add 하기 전까지는 Git이 변경사항을 무시
- 여러 파일을 수정했을 때 **원하는 것만 골라서** 커밋할 수 있게 해줌

---

### git commit — 로컬 저장소에 저장

스테이징된 변경사항을 **로컬 저장소에 스냅샷으로 기록**

```bash
git commit -m "feat: Add collaboration plan"
```

- 이 시점에서 변경 이력이 로컬에 영구 저장됨
- 아직 GitHub에는 반영되지 않음 → **내 PC에만 존재**
- 커밋은 되돌리거나 수정할 수 있어 push 전에 검토 가능

---

### git push — 원격 저장소(GitHub)에 업로드

로컬 커밋을 **GitHub에 업로드**해서 팀원들이 볼 수 있게 함

```bash
git push origin Database_Design
```

- 이 시점부터 팀원이 변경사항을 받아볼 수 있음
- push 이후 커밋을 수정하면 팀원과 충돌 발생 가능 → 신중하게

---

## 이 프로젝트에서의 흐름 예시

```bash
# 1. 본인 브랜치에서 파일 수정

# 2. 변경사항 확인
git status

# 3. 스테이징
git add docs/COLLABORATION.md
git add Database_Design/plans/PLAN_00_MASTER.md

# 4. 로컬에 커밋
git commit -m "feat: Add collaboration plan and update migration docs for VPC"

# 5. GitHub에 push
git push origin Database_Design

# 6. 작업 완료 후 main에 반영하려면 GitHub에서 PR 생성
```

---

## 한 줄 요약

| 명령어 | 저장 위치 | 팀원 공유 여부 | 되돌리기 |
|--------|---------|------------|---------|
| `git add` | 로컬 스테이징 영역 | X | 쉬움 |
| `git commit` | 로컬 저장소 | X | 가능 (push 전) |
| `git push` | GitHub | O | 어려움 (팀원 영향) |

**add → commit → push** 순서로 범위가 점점 넓어진다고 보면 됩니다.

---

## 주의사항

1. **`.env` 파일은 절대 add하지 않는다** — DB 접속 정보 유출 위험
2. **main 브랜치에 직접 push하지 않는다** — 반드시 PR을 통해 병합
3. **push 전에 `git status`로 반드시 확인** — 의도하지 않은 파일이 포함되지 않았는지 체크
