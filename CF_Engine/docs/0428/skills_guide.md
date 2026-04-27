# CF_Engine Skills 가이드

**경로**: `CF_Engine/skills/`  
**용도**: 논문 작성·문헌 조사·문서 품질 관리를 위한 Claude Code 스킬 모음  
**작성일**: 2026-04-28

---

## 스킬 목록

| 스킬 | 폴더 | 언어 | 주요 용도 |
|------|------|------|----------|
| literature-review | `skills/literature-review/` | 영문 | 학술 문헌 체계적 검색·검증·리뷰 |
| scientific-writing | `skills/scientific-writing/` | 영문 | 학술 논문 구조·문단 작성 |
| humanizer (v2.1.1) | `skills/humanizer/` | 영문 | AI 작성 흔적 제거 |
| humanizer (v2.5.1) | `skills/humanizer-main/` | 영문 | AI 작성 흔적 제거 (최신) |
| grammar-checker | `skills/korean-skills-main/skills/grammar-checker/` | 한국어 | 맞춤법·띄어쓰기·문법 검사 |
| humanizer (한국어) | `skills/korean-skills-main/skills/humanizer/` | 한국어 | AI 작성 패턴 탐지·교정 |
| style-guide | `skills/korean-skills-main/skills/style-guide/` | 한국어 | 문서 내 용어·어조 일관성 검사 |

---

## 스킬별 상세 설명

### 1. literature-review

**파일**: `skills/literature-review/SKILL.md`  
**버전**: —

#### 역할
PubMed, arXiv, Semantic Scholar 등 다중 학술 DB를 체계적으로 검색하고, 인용 검증 및 PDF 생성까지 수행하는 학술 문헌 리뷰 자동화 스킬.

#### 주요 기능
- 다중 DB 병렬 검색 (PubMed, arXiv, Semantic Scholar, bioRxiv 등)
- DOI 기반 인용 정확도 자동 검증 (`scripts/verify_citations.py`)
- 검색 결과 중복 제거·스크리닝·데이터 추출 워크플로우 안내
- APA / Nature / Vancouver / IEEE 인용 스타일 지원
- Markdown → PDF 변환 (`scripts/generate_pdf.py`)
- PRISMA 다이어그램 등 시각 자료 생성 안내

#### 포함 스크립트

| 스크립트 | 역할 |
|---------|------|
| `scripts/verify_citations.py` | DOI 검증 및 CrossRef 메타데이터 조회 |
| `scripts/generate_pdf.py` | Markdown → PDF 변환 (pandoc/xelatex) |
| `scripts/search_databases.py` | 검색 결과 중복 제거·포맷 변환 |

#### 이 프로젝트에서 활용 예시
- `0427hybrid_recommendation.md` 참고문헌 [1]~[11] 인용 정확도 검증
- 추천 시스템 관련 선행 연구 조사 (NDCG 평가 방법론, ALS 성능 비교 등)

---

### 2. scientific-writing

**파일**: `skills/scientific-writing/SKILL.md`  
**버전**: —

#### 역할
IMRAD 구조(서론-방법-결과-토론) 기반 학술 논문 작성을 단계별로 안내하는 스킬. 아웃라인(불릿) → 완전한 문단으로 변환하는 2단계 작성 프로세스를 핵심으로 한다.

#### 주요 기능
- IMRAD 구조 기반 초고 작성 프로세스
- "아웃라인(불릿) → 완전한 문단" 2단계 작성 방법론 강제
- AMA / Vancouver / APA / IEEE / Chicago 인용 스타일
- CONSORT · STROBE · PRISMA 등 연구 유형별 보고 가이드라인 체크리스트
- 분야별 전문 용어 관습 (생의학·화학·신경과학·컴퓨터과학 등)
- Abstract, Introduction, Methods, Results, Discussion 섹션별 세부 지침

#### 포함 참조 문서

| 파일 | 내용 |
|------|------|
| `references/imrad_structure.md` | IMRAD 섹션별 작성 가이드 |
| `references/citation_styles.md` | 인용 스타일 전체 가이드 |
| `references/figures_tables.md` | 그림·표 디자인 원칙 |
| `references/reporting_guidelines.md` | 연구 유형별 보고 체크리스트 |
| `references/writing_principles.md` | 과학적 글쓰기 핵심 원칙 |

#### 이 프로젝트에서 활용 예시
- `0427hybrid_recommendation.md` 논문 구조 검토
- 결과 섹션(6절) 문단 흐름 점검

---

### 3. humanizer (영문, v2.1.1)

**파일**: `skills/humanizer/SKILL.md`  
**버전**: 2.1.1

#### 역할
Wikipedia "Signs of AI writing" 기준으로 AI 생성 영문 텍스트의 특징 패턴을 탐지하고 자연스러운 인간 글쓰기로 교정하는 스킬.

#### 탐지·교정 패턴 (24가지)

| 카테고리 | 대표 패턴 |
|---------|----------|
| 콘텐츠 | 과장 중요성 부여, 홍보성 언어, `-ing` 형 피상 분석, 모호한 출처 |
| 어휘·문법 | AI 과용 단어(pivotal·landscape·testament), copula 회피, 부정 병렬 구문, 3박자 나열 |
| 스타일 | em dash 과다, 볼드 남용, 불릿 헤더, 이모지 |
| 소통 | 챗봇 표현 잔재, 지식 차단일 면책, 과도한 헤징 |

#### humanizer vs humanizer-main 차이

| 항목 | humanizer (v2.1.1) | humanizer-main (v2.5.1) |
|------|-------------------|------------------------|
| 패턴 수 | 24가지 | 29가지 |
| 자가 검수 | 없음 | **추가** ("What makes this AI-generated?" 자가 감사 후 재수정) |
| 보이스 매칭 | 없음 | **추가** (사용자 글쓰기 샘플 기반 어조 매칭) |
| passive voice | 미포함 | **추가** |
| hyphenated pairs 과다 | 미포함 | **추가** |
| signposting | 미포함 | **추가** |

> **권장**: 최신 버전인 `humanizer-main` (v2.5.1) 사용

---

### 4. humanizer-main (영문, v2.5.1)

**파일**: `skills/humanizer-main/SKILL.md`  
**버전**: 2.5.1  
**라이선스**: MIT

#### 역할
v2.1.1의 업그레이드 버전. 29가지 패턴 탐지 + 자가 검수 패스 포함.

#### v2.5.1 추가 패턴

| 패턴 | 설명 |
|------|------|
| Passive voice & subjectless fragments | 행위자 생략 피동문 ("No config needed") |
| Hyphenated word pair 과다 | `cross-functional`, `data-driven` 등 일관된 하이픈 |
| Persuasive authority tropes | "The real question is", "At its core" |
| Signposting & announcements | "Let's dive in", "Here's what you need to know" |
| Fragmented headers | 헤딩 직후 헤딩 내용을 되풀이하는 1줄 문단 |

#### 자가 검수 2단계 프로세스
1. 초안 재작성
2. "What makes the below so obviously AI generated?" 자가 진단
3. 남은 패턴 제거 후 최종본 출력

---

### 5. grammar-checker (한국어)

**파일**: `skills/korean-skills-main/skills/grammar-checker/SKILL.md`  
**버전**: 1.0.1  
**라이선스**: MIT (작성자: DaleSeo)

#### 역할
국립국어원 표준 한국어 규정 기반 맞춤법·띄어쓰기·문법 구조·구두점 검사 및 교정.

#### 검사 우선순위

| 우선순위 | 카테고리 | 대표 오류 |
|---------|---------|----------|
| 1 (최고) | 맞춤법/철자 | 되요→돼요, 안→않 |
| 2 (높음) | 띄어쓰기 | 할수있다→할 수 있다 |
| 3 (중간) | 문법 구조 | 조사(책를→책을), 어미 |
| 4 (낮음) | 구두점 | 쉼표 과다, 가운뎃점 오남용 |

#### 출력 형식
- 오류 유형별 분류
- ❌/✅/📝/🔍 아이콘으로 확신도 표시
- 교정된 전체 텍스트 제공
- 오류 이유·규칙 교육적 설명

#### 이 프로젝트에서 활용 예시
- `0427hybrid_recommendation.md` 한국어 본문 맞춤법 최종 점검
- 실험 보고서(`docs/`) 작성 후 검토

---

### 6. humanizer (한국어)

**파일**: `skills/korean-skills-main/skills/humanizer/SKILL.md`  
**버전**: 1.3.0  
**라이선스**: MIT (작성자: DaleSeo)

#### 역할
KatFishNet 논문(arXiv 2503.00032v4) 기반 한국어 AI 작성 패턴 24가지를 과학적으로 탐지하고 자연스러운 한국어로 교정.

#### 과학적 근거 (KatFishNet 논문)

| 패턴 카테고리 | AUC | 대표 특징 |
|------------|-----|----------|
| 문장부호 (7가지) | **94.88%** | 쉼표 과다(AI 61% vs 인간 26%), 영어식 배치 |
| 품사 다양성 (3가지) | **82.99%** | 명사 과다, 동사·형용사 빈곤 |
| 띄어쓰기 (3가지) | **79.51%** | 의존명사 띄어쓰기 경직 (SD=0.02) |
| 어휘 (7가지) | 중간 | AI 유행어, 불필요한 한자어, 복수형 남용 |
| 구조 (4가지) | 중간 | 3박자 나열, 단조로운 문장 리듬 |

#### 영문 humanizer와의 차이
- 한국어 전용 (영어 번역 미포함)
- 언어학 논문 실증 데이터 기반 (영문은 Wikipedia 관찰 기반)
- 쉼표 패턴 탐지 AUC 94.88%로 가장 높은 정확도

---

### 7. style-guide (한국어)

**파일**: `skills/korean-skills-main/skills/style-guide/SKILL.md`  
**버전**: 1.0.0  
**라이선스**: MIT (작성자: DaleSeo)

#### 역할
문법 오류가 아닌 **스타일 일관성**에 집중. 동일 문서·프로젝트 내 어조·용어·형식 불일치를 감지하고 통일안을 제시.

#### 검사 7가지 카테고리

| 우선순위 | 카테고리 | 대표 불일치 |
|---------|---------|-----------|
| 1 (최고) | 어조·격식 | `입니다` ↔ `이에요` 혼용 |
| 2 (높음) | 용어 통일 | `사용자` ↔ `유저` ↔ `이용자` |
| 3 (중간) | 숫자·단위 | `3개` ↔ `세 개` |
| 3 (중간) | 목록 구조 | `-` ↔ `•` ↔ `1.` 혼용 |
| 4 (낮음) | 인용·강조 | `""` ↔ `''` ↔ `「」` |
| 4 (낮음) | 날짜·시간 | `2026년 1월 27일` ↔ `2026.01.27` |
| 4 (낮음) | 링크·참조 | 링크 텍스트 스타일 |

#### 권위 출처
- 국립국어원 쉬운 공문서 쓰기 길잡이 (2022)
- Kakao Enterprise 기술문서 작성 가이드
- 대학 학위논문 작성 지침

#### 이 프로젝트에서 활용 예시
- `0427hybrid_recommendation.md`의 `CF` → `협업필터링` 용어 통일 작업에 적용

---

## 스킬 선택 가이드

```
작업 유형에 따라 스킬 선택:

논문 참고문헌 검색·검증
  └─ literature-review

논문 섹션 작성 (서론/방법/결과/토론)
  └─ scientific-writing

영문 텍스트 AI 흔적 제거
  └─ humanizer-main (v2.5.1 권장)

한국어 텍스트 AI 흔적 제거
  └─ korean-skills-main/humanizer

한국어 맞춤법·문법 검사
  └─ korean-skills-main/grammar-checker

문서 내 용어·어조 일관성 통일
  └─ korean-skills-main/style-guide
```

---

## Claude Code에서 스킬 호출 방법

```bash
# literature-review 스킬로 인용 검증 요청 예시
/literature-review 0427hybrid_recommendation.md의 참고문헌 검증해줘

# style-guide 스킬로 용어 통일 요청 예시
/style-guide CF 관련 키워드를 협업필터링 또는 ALS행렬분해로 통일해줘

# grammar-checker로 맞춤법 검사 예시
/grammar-checker docs/progress_report_20260318.md 검사해줘
```

> Claude Code 프로젝트 설정에 skills 경로가 등록된 경우에만 `/스킬명` 슬래시 명령으로 직접 호출 가능.
