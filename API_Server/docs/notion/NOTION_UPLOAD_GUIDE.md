# Notion 업로드 작업 가이드

> 작성일: 2026-03-20 | 작성자: 조장(dhwang0803)
> 상태: 진행 중 (토큰 인증 대기)

---

## 1. 목표

`API_Server/docs/notion/` 디렉토리의 22개 기술 문서를
Notion 워크스페이스의 **Development 데이터베이스**에 업로드한다.

### Notion 대상 경로

```
HwangThomas님의 워크스페이스 / 2차 프로젝트 1조 / Development (데이터베이스)
```

---

## 2. 소스 문서 목록 (22개)

| # | 파일명 | 제목 |
|---|--------|------|
| 00 | `00_시스템_개요.md` | API_Server 시스템 개요 |
| 01 | `01_인증_JWT발급.md` | POST /auth/token — JWT 발급 |
| 02 | `02_홈_배너.md` | GET /home/banner — 히어로 배너 |
| 03 | `03_홈_섹션.md` | GET /home/sections — CT_CL별 인기 섹션 |
| 04 | `04_VOD_상세.md` | GET /vod/{asset_id} — VOD 상세 |
| 05 | `05_시리즈_에피소드목록.md` | GET /series/{id}/episodes — 에피소드 목록 |
| 06 | `06_시리즈_시청진행.md` | GET /series/{id}/progress — 시청 진행 |
| 07 | `07_시리즈_진행률기록.md` | POST /series/{id}/episodes/{ep}/progress — 진행률 기록 |
| 08 | `08_시리즈_구매확인.md` | GET /series/{id}/purchase-check — 구매 확인 |
| 09 | `09_시리즈_구매옵션.md` | GET /series/{id}/purchase-options — 구매 옵션 |
| 10 | `10_구매_포인트결제.md` | POST /purchases — 포인트 결제 |
| 11 | `11_찜_추가.md` | POST /wishlist — 찜 추가 |
| 12 | `12_찜_해제.md` | DELETE /wishlist/{series_nm} — 찜 해제 |
| 13 | `13_마이_시청중.md` | GET /user/me/watching — 시청 중 |
| 14 | `14_마이_프로필.md` | GET /user/me/profile — 프로필 |
| 15 | `15_마이_포인트.md` | GET /user/me/points — 포인트 |
| 16 | `16_마이_시청내역.md` | GET /user/me/history — 시청 내역 |
| 17 | `17_마이_구매내역.md` | GET /user/me/purchases — 구매 내역 |
| 18 | `18_마이_찜목록.md` | GET /user/me/wishlist — 찜 목록 |
| 19 | `19_추천_개인화.md` | GET /recommend/{user_id} — 개인화 추천 |
| 20 | `20_추천_유사콘텐츠.md` | GET /similar/{asset_id} — 유사 콘텐츠 |
| 21 | `21_광고_팝업.md` | WS /ad/popup — 광고 팝업 |

---

## 3. Notion 템플릿 구조 (SWDEV-개발 문서 템플릿)

Notion Development DB에 올릴 각 페이지는 아래 템플릿을 따른다.

```
# SWDEV-{문서제목}

## 기능 개요
- 기능/모듈명:
- 목적(Why):
- 범위(In/Out):
  - 포함(In):
  - 제외(Out):
- 사용자/대상(Who):
- 관련 문서/티켓:
  - PRD/요구사항:
  - 이슈/티켓:
  - 설계/회의록:

---

## 기본 동작
- 전제 조건(Preconditions):
- 트리거(Trigger):

### 입력(Input)
- 입력 데이터 형식/필드:
- 유효성 규칙:

### 처리 흐름(Process)
1.
2.
3.

### 출력(Output)
- 반환/응답 형식:
- 저장/발행되는 데이터:

### 로그/모니터링
- 주요 로그 포인트:
- 지표/알람:

---

## 예외 사항

### 입력 오류
- 케이스:
- 시스템 동작(에러 코드/메시지/처리):
- 복구/재시도 정책:

### 외부 의존성 오류
- 타임아웃/5xx/Rate limit:
- Backoff/재시도 정책:

### 데이터 불일치/경합(Concurrency)
- 중복 요청/멱등성(Idempotency):
- 락/트랜잭션/정합성:

### 권한/인증
- 권한 부족 시 처리:

---

## 제약 사항

### 성능
- 목표 지연시간/처리량(SLO/SLA):
- 병목 예상 구간:

### 자원/환경
- 실행 환경(Dev/Stage/Prod):
- 메모리/CPU/스토리지 제한:

### 보안/개인정보
- 민감정보 처리/마스킹:
- 접근 제어:

### 운영
- 배포 전략(점진/블루그린/롤백):
- Feature flag 여부:

### 호환성
- 지원 버전/클라이언트:

---

## 업스트림 & 다운스트림 의존성

### 업스트림(Upstream)
- 시스템/서비스:
- 인터페이스(API/Queue/DB):
- 계약(Contract):
  - 엔드포인트/토픽/테이블:
  - 스키마/필드:
  - 변경 영향/버전 정책:

### 다운스트림(Downstream)
- 시스템/서비스:
- 인터페이스(API/Queue/DB):
- 계약(Contract):
  - 엔드포인트/토픽/테이블:
  - 스키마/필드:
  - 장애/지연 시 영향:
```

---

## 4. 매핑 전략 (기존 docs/notion → 템플릿)

기존 문서의 6섹션 구조를 템플릿의 상세 구조로 확장 매핑한다.

| 기존 섹션 | 템플릿 매핑 대상 | 매핑 방식 |
|-----------|-----------------|-----------|
| `# 제목` | 페이지 이름 (`이름` 속성) | 그대로 사용 |
| `## 기능 개요` | `## 기능 개요` 전체 | 기능명/목적/범위/대상 세분화 |
| `## 기본 기능` (요청/처리/응답) | `## 기본 동작` (입력/처리흐름/출력) | 요청→입력, SQL→처리흐름, JSON응답→출력 |
| `## 예외사항` | `## 예외 사항` (입력오류/권한) | 에러코드 테이블 → 케이스별 분류 |
| `## 제약사항` | `## 제약 사항` (성능/보안/운영) | 인증/비즈니스룰 → 보안/호환성으로 재분류 |
| `## 업스트림 의존성` | `## 업스트림 & 다운스트림` (업스트림) | 테이블/컬럼 → 계약(Contract) 형식 |
| `## 다운스트림 의존성` | `## 업스트림 & 다운스트림` (다운스트림) | 동일 |

### 기존에 없어서 추가 필요한 항목

| 템플릿 항목 | 채울 내용 | 비고 |
|------------|-----------|------|
| 관련 문서/티켓 | GitHub PR/이슈 번호 | 있는 경우만 |
| 전제 조건 | 인증 필수 여부, 선행 API 호출 | 기존 제약사항에서 추출 |
| 유효성 규칙 | limit 범위, 필수 파라미터 | 기존 기본 기능에서 추출 |
| 로그/모니터링 | 미구현 → "TBD" | 현재 로깅 미설계 |
| 외부 의존성 오류 | DB 타임아웃 처리 | "TBD" |
| 멱등성 | POST 엔드포인트만 해당 | UPSERT 여부 기반 |
| 성능 SLO | 미정 → "TBD" | |
| 배포 전략 | 미정 → "TBD" | |

---

## 5. Notion API 연동 방식

### 사용 도구

Claude Code MCP (Notion API 플러그인) — `@notionhq/notion-mcp-server`

### MCP 서버 설정 현황

- **설정 위치**: `~/.claude.json` → `projects["dxshcool-dhwang0803"].mcpServers.notion-api`
- **서버 명령**: `cmd /c npx -y @notionhq/notion-mcp-server`
- **인증**: `OPENAPI_MCP_HEADERS` 환경변수 (Windows User 환경변수로 등록)
- **토큰 타입**: Notion Internal Integration (`ntn_*`)

### 인증 설정 순서

1. Notion Integration 생성 (https://www.notion.so/profile/integrations)
   - 이름: 자유
   - 기능: Content Read/Insert/Update + Comments Read/Insert
2. Windows 시스템 환경변수 등록 (보안상 파일 저장 대신 OS 레벨 관리)
   ```powershell
   [System.Environment]::SetEnvironmentVariable(
     'OPENAPI_MCP_HEADERS',
     '{"Authorization":"Bearer ntn_토큰값","Notion-Version":"2022-06-28"}',
     'User'
   )
   ```
3. **VSCode 재시작** (환경변수 반영에 필수)
4. Notion 페이지에서 Integration 연결 추가 (···→ 연결 추가)

### 업로드 API 호출 순서

```
문서 1개당:
  1. API-post-page     → Development DB에 행(페이지) 생성 (이름 속성 설정)
  2. API-patch-block-children → 페이지 본문에 블록 추가
     - paragraph 블록: 일반 텍스트
     - bulleted_list_item 블록: 목록 항목
     (Notion API는 마크다운 직접 지원 X → 블록 단위 변환 필요)
```

### 제한사항

- Notion API는 한 번의 `patch-block-children` 호출에 최대 100개 블록
- 헤딩(h1/h2/h3), 코드블록, 테이블은 MCP 스키마상 paragraph/bulleted_list_item만 지원
  → 헤딩은 볼드 텍스트로 대체하거나, 별도 블록 타입 확인 필요
- Rate limit: Notion API 3 req/sec

---

## 6. 현재 상태 & 남은 작업

### 완료

- [x] docs/notion/ 22개 문서 생성 완료
- [x] Notion Development 데이터베이스 생성 완료 (빈 상태)
- [x] MCP 서버 등록 완료 (`notion-api`)
- [x] SWDEV 템플릿 구조 확인 완료
- [x] 매핑 전략 수립 완료
- [x] Windows 환경변수 `OPENAPI_MCP_HEADERS` 등록 완료

### 대기

- [ ] VSCode 재시작 (백그라운드 스크립트 완료 대기)
- [ ] MCP 인증 테스트 (`API-get-self` 호출)

### 실행 예정

- [ ] Development DB의 database_id 확인 (API-post-search)
- [ ] 22개 문서를 템플릿 형식으로 확장 매핑
- [ ] Notion 페이지 22개 생성 + 본문 블록 추가
- [ ] 업로드 결과 검증

---

## 7. 팀원 작업 가이드 (향후 제공용)

### 새 기능 문서 추가 시

1. `docs/notion/` 에 `{번호}_{기능명}.md` 파일 생성
2. SWDEV 템플릿 구조에 맞춰 내용 작성
3. Claude Code에서 Notion 업로드 실행
   - 또는 직접 Notion Development DB에서 "새로 만들기" → 템플릿 선택

### 기존 문서 수정 시

1. `docs/notion/` 소스 파일 수정
2. Notion 페이지도 동기화 (수동 또는 스크립트)
3. **소스(Git)가 SSoT** — Notion은 공유용 뷰

---

## 부록: 참고 파일 경로

| 파일 | 용도 |
|------|------|
| `API_Server/docs/notion/*.md` | 소스 문서 22개 |
| `API_Server/docs/error_message_policy.md` | 에러 코드 정책 (예외사항 매핑 참고) |
| `API_Server/docs/프론트엔드_요구사항(협의필요).md` | 팀 결정사항 반영 현황 |
| `API_Server/CLAUDE.md` | 엔드포인트/인터페이스 정의 |
| `~/.claude.json` | MCP 서버 설정 (notion-api) |
