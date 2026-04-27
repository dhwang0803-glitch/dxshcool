# 다음 세션 작업 목록

**작성일**: 2026-04-28  
**관련 문서**: `CF_Engine/0427hybrid_recommendation.md`

---

## 1. 논문 내 용어 통일 미완료 항목 (우선순위 높음)

이번 세션에서 `CF` → `협업필터링`, `ALS` → `ALS 행렬분해`로 통일했으나,
원래부터 한국어로 작성된 아래 3곳은 변경하지 않았음. **통일 여부 결정 필요.**

| 위치 | 현재 표기 | 통일 시 수정안 |
|------|----------|--------------|
| line 11 핵심어 | `협업 필터링` (띄어쓰기) | `협업필터링` |
| line 104 4.1절 섹션 헤딩 | `협업 필터링 (Collaborative Filtering)` | `협업필터링 (Collaborative Filtering)` |
| line 126 4.3절 본문 | `협업 필터링과 벡터 유사도 추천의 후보를` | `협업필터링과 벡터 유사도 추천의 후보를` |

> 국립국어원 기준으로 `협업 필터링`(띄어쓰기)과 `협업필터링`(붙여쓰기) 모두 허용.
> 논문 전체에서 한 가지로 통일하는 것을 권장.

---

## 2. 참고문헌 [3] 저자 표기 확인 (우선순위 중간)

현재 표기:
```
[3] J. McAuley, C. Targett, Q. Shi, and A. van den Hengel
```

논문 원문에서 van den Hengel의 이니셜이 `A.`인지 확인 필요.  
(ACM DL 기준 저자명: Anton van den Hengel — `A.` 맞음, 현재 정확)

---

## 3. git 파일 관리 미결 사항 (우선순위 중간)

### 3-1. `CF_Engine/skills/` 폴더 push 여부
- 현재: untracked 상태 (미commit)
- 포함 시: `git add CF_Engine/skills/` 후 push
- 미포함 시: `.gitignore`에 `CF_Engine/skills/` 추가 권장

### 3-2. `.env.example` 삭제 처리
- 현재: `git status`에서 삭제된 것으로 표시됨
- 의도한 삭제라면: `git add -u .env.example` 후 commit
- 실수라면: `git restore .env.example` 로 복구

---

## 4. IDE 표시 문제 (우선순위 낮음 — 자동 해결)

사용자 IDE에서 `NCF`가 `NALS행렬분해`로 보이는 캐시 문제.  
다른 컴퓨터에서 `git pull` 후 파일을 열면 정상(NCF)으로 표시됨.  
현재 이 컴퓨터에서도 파일을 닫고 다시 열면 해결됨.

---

## 5. 논문 본문 추가 작업 (우선순위 작성자 판단)

현재 `0427hybrid_recommendation.md`는 완성된 논문 형태.  
추가 작업이 필요한 경우 아래 스킬 활용:

| 작업 | 사용할 스킬 |
|------|-----------|
| 참고문헌 추가·검증 | `literature-review` |
| 본문 섹션 보완 | `scientific-writing` |
| 한국어 맞춤법 최종 점검 | `korean-skills-main/grammar-checker` |
| AI 문체 제거 | `korean-skills-main/humanizer` |

스킬 상세 설명 → `CF_Engine/docs/skills_guide.md`

---

## 완료된 작업 (이번 세션)

- [x] `CF` 약자 → `협업필터링` 치환 (15건)
- [x] `ALS` 약자 → `ALS 행렬분해` 치환 (7건)
- [x] 참고문헌 [1]~[11] 전체 인용 정확도 검증
- [x] 참고문헌 [10] 연도 오류 수정 (2016 → 2015)
- [x] 인용 검증 보고서 작성 (`docs/citation_verification_report_0427.md`)
- [x] 문서 수정 이력 보고서 작성 (`docs/revision_report_0427.md`)
- [x] Skills 가이드 문서 작성 (`docs/skills_guide.md`)
