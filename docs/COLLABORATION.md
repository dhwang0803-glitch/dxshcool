# VOD 추천 시스템 - 협업 플랜

**프로젝트**: VOD 추천 시스템
**팀 구성**: 5명 (담당자 A ~ E)
**작성일**: 2026-03-07

---

## 전체 Phase 구조

```
Phase 1:   DB 설계 및 초기 데이터 VPC 업로드     ← 전원 참여
Phase 2-1: RAG 메타데이터 보충                   ← 담당자 B
Phase 2-2: VOD 임베딩                            ← 담당자 C
Phase 2-3: 시청패턴 임베딩                        ← 담당자 D
Phase 3:   행렬분해 추천                          ← 담당자 D
Phase 4:   사물인식 + 지자체 광고/제철장터 연동    ← 담당자 E
Phase 5:   웹서비스 통합                          ← 전원
```

---

## 담당자별 역할 요약

| 담당자 | Phase 1 역할 | 이후 담당 Phase |
|--------|-------------|----------------|
| A | DB 설계 완료 + VPC/Docker 관리 + user 테이블 업로드 (600K) | Phase 5 웹서비스 DB 연동 |
| B | vod 테이블 업로드 + .env 파일 팀 배포 | Phase 2-1 RAG + 콘텐츠 기반 추천 |
| C | watch_history 업로드 (2025-01-01 ~ 2025-01-10) | Phase 2-2 VOD 임베딩 |
| D | watch_history 업로드 (2025-01-11 ~ 2025-01-20) | Phase 2-3 시청패턴 임베딩 → Phase 3 행렬분해 추천 |
| E | watch_history 업로드 (2025-01-21 ~ 2025-01-31) | Phase 4 사물인식 + 지자체 광고/제철장터 연동 |

---

## Phase 1: DB 설계 및 초기 데이터 VPC 업로드 (상세)

### 1-1. 사전 준비 (전원)

#### .env 파일 설정
담당자 A가 VPC 환경 구성 후 팀 내 별도 채널(Git 외)로 배포.

```
DB_HOST=<VPC_IP>
DB_PORT=5432
DB_NAME=vod_db
DB_USER=<username>
DB_PASSWORD=<password>
```

> `.gitignore`에 `.env` 추가 필수

#### 로컬 Python 환경 세팅

```bash
conda activate myenv
pip install -r requirements.txt
```

#### CSV 파일 VPC 업로드 (각자 담당 파일)

```bash
scp ./data/<파일명>.csv <user>@<VPC_IP>:/home/<user>/vod_data/
```

---

### 1-2. 업로드 순서 (FK 의존성)

```
Step 1 [A, B 동시]:    user 테이블 + vod 테이블 업로드
                                ↓
Step 2 [C, D, E 동시]: watch_history 분할 업로드 (Step 1 완료 후 시작)
```

#### watch_history 날짜 분할 기준

| 담당자 | strt_dt 범위 | 예상 건수 |
|--------|-------------|---------|
| C | 2025-01-01 ~ 2025-01-10 | 약 14M |
| D | 2025-01-11 ~ 2025-01-20 | 약 14M |
| E | 2025-01-21 ~ 2025-01-31 | 약 16M |

중복 방지 (migrate.py에 적용):
```sql
ON CONFLICT (user_id_fk, vod_id_fk, strt_dt) DO NOTHING;
```

---

### 1-3. DB 연결 테스트 (전원)

업로드 완료 후 전원이 아래 쿼리로 직접 확인:

```sql
-- 1. 접속 확인
SELECT version();

-- 2. 건수 검증
SELECT
    (SELECT COUNT(*) FROM "user")        AS user_count,   -- 기대: 600,000
    (SELECT COUNT(*) FROM vod)           AS vod_count,
    (SELECT COUNT(*) FROM watch_history) AS watch_count;  -- 기대: 44,000,000
```

---

### 1-4. Phase 1 완료 기준

- [ ] 담당자 A: DB 스키마 배포 완료 (create_tables.sql, create_indexes.sql 실행)
- [ ] 담당자 A: VPC PostgreSQL Docker 컨테이너 정상 구동 확인
- [ ] 담당자 B: .env 파일 전원 배포 완료
- [ ] 전원: DB 접속 성공 확인
- [ ] 전원: 건수 검증 통과 (user / vod / watch_history)

---

## Phase 2-1: RAG 메타데이터 보충

**담당**: 담당자 B
**연계**: vod 테이블 업로드 → RAG 보충 → 콘텐츠 기반 추천 (Phase 5)

- 로컬 LLM으로 `director`, `smry` NULL 항목 보충
- `ct_cl` 기준으로 VOD 분류 후 순차 처리
- 처리 완료 시 `rag_processed = TRUE`, `rag_processed_at` 업데이트
- 중복 방지: 작업 전 `WHERE rag_processed = FALSE` 조건으로 대상 조회

```sql
-- 진행 현황 확인
SELECT ct_cl,
       COUNT(*) FILTER (WHERE rag_processed) AS done,
       COUNT(*)                               AS total
FROM vod
GROUP BY ct_cl;
```

---

## Phase 2-2: VOD 임베딩

**담당**: 담당자 C
**연계**: VOD 메타데이터 → 임베딩 생성 → Phase 3 행렬분해 입력값

- 로컬에서 임베딩 연산 후 결과만 VPC DB에 저장
- `vod_embedding` 테이블에 INSERT
- 중복 방지: `embedding_processed` 컬럼으로 처리 여부 추적

---

## Phase 2-3: 시청패턴 임베딩

**담당**: 담당자 D
**연계**: watch_history → 유저 임베딩 생성 → Phase 3 행렬분해 입력값

- 로컬에서 임베딩 연산 후 결과만 VPC DB에 저장
- `user_embedding` 테이블에 INSERT
- user_id 범위 기준 분할 처리 가능

---

## Phase 3: 행렬분해 추천

**담당**: 담당자 D
**연계**: VOD 임베딩 + 시청패턴 임베딩 → 추천 결과 생성 → Phase 5

- 전체 임베딩 데이터 필요 → VPC DB에서 읽어 로컬에서 연산
- 고사양 로컬 PC 사용 권장 (VPC 1core/4GB로 연산 불가)
- 추천 결과를 `vod_recommendation` 테이블에 저장

---

## Phase 4: 사물인식 + 지자체 광고/제철장터 연동

**담당**: 담당자 E
**연계**: VOD 영상 분석 → 광고 트리거 매칭 → Phase 5

> **2026-03-19 방향 전환**: 홈쇼핑 연동 폐기 → 지자체 광고 팝업 + 제철장터 채널 연계로 전환.

- VOD 영상 YOLO/CLIP/STT 3종 배치 인식 (로컬 처리)
- 관광지/지역 인식 → 지자체 광고 팝업 (생성형 AI 제작, OCI 저장)
- 음식 인식 → 제철장터 채널 상품 연계 (채널 이동/시청예약)

---

## Phase 5: 웹서비스 통합

**담당**: 전원 (각자 담당 모듈 연동)

| 담당자 | 웹서비스 담당 모듈 |
|--------|----------------|
| A | DB API 설계 및 쿼리 최적화 지원 |
| B | 콘텐츠 기반 추천 API (메타데이터, 신작, 조회수 기반) |
| C | VOD 벡터 검색 API |
| D | 행렬분해 추천 API |
| E | 사물인식 + 지자체 광고/제철장터 API |

---

## 브랜치 전략

```
main                    ← 최종 통합 (PR로만 병합, 단독 push 금지)
├── Database_Design     ← 담당자 A (DB 스키마 + 마이그레이션)
├── RAG                 ← 담당자 B (메타데이터 수집)
├── VOD_Embedding       ← 담당자 C (CLIP 512 + 메타 384 임베딩)
├── User_Embedding      ← 담당자 D (ALS 행렬분해 896D)
├── Poster_Collection   ← 담당자 C (TMDB/Tving 포스터 수집)
├── CF_Engine           ← 담당자 D (협업 필터링 추천)
├── Vector_Search       ← 담당자 B (벡터 유사도 검색)
├── Hybrid_Layer        ← 담당자 A (CF+Vector 리랭킹)
├── gen_rec_sentence    ← 담당자 A (세그먼트별 추천 문구)
├── Object_Detection    ← 담당자 E (YOLO/CLIP/STT 사물인식)
├── Shopping_Ad         ← 담당자 E (지자체 광고 + 제철장터)
├── API_Server          ← 전원 (FastAPI 백엔드)
└── Frontend            ← 전원 (React/Next.js)
```

---

## 협업 규칙

1. **DB 스키마 변경**: 담당자 A에게 사전 공유 후 PR로 반영
2. **.env 파일**: Git 커밋 금지, 팀 내 별도 채널로 공유
3. **main 병합**: 반드시 PR + 1명 이상 리뷰 후 병합
4. **중복 방지**: `rag_processed`, `embedding_processed` 컬럼 확인 후 작업 시작
5. **무거운 연산**: 로컬에서 처리 후 결과만 VPC DB에 저장
