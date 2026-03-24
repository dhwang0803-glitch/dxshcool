# VOD_Embedding 모듈 현황 보고서

**작성일**: 2026-03-11
**대상 브랜치**: `VOD_Embedding`
**목적**: 모듈 구조·코드 로직·현재 진행 상태 파악

---

## 1. 한눈에 보는 구조

```
VOD_Embedding/
├── CLAUDE.md                    ← 브랜치 전용 지침 (기술 스택, 폴더 규칙)
├── README.md                    ← 팀원 온보딩 가이드 (분산 작업용)
├── .gitignore                   ← pkl·webm·.env 제외
├── agents/                      ← TDD 에이전트 역할 정의 (7개)
├── config/                      ← 현재 비어있음 (.gitkeep)
├── data/                        ← 실행 결과 저장 (gitignore 대상)
├── docs/
│   ├── plans/                   ← 단계별 상세 계획 (PLAN 00~03)
│   └── reports/
│       └── report.md            ← 파일럿 100건 실행 결과 리포트
└── scripts/                     ← 실행 스크립트 3개 (전체 파이프라인)
    ├── crawl_trailers.py        ← PLAN_01: YouTube 트레일러 수집
    ├── batch_embed.py           ← PLAN_02: CLIP 임베딩
    └── ingest_to_db.py          ← PLAN_03: pgvector DB 적재
```

> `src/`는 .gitkeep만 존재 — 아직 공유 라이브러리 모듈화 전

---

## 2. 3단계 파이프라인

```
[vod 테이블]
    │  asset_nm, ct_cl, genre, series_nm 조회
    ▼
[PLAN_01] crawl_trailers.py
    • YouTube 검색 쿼리 생성
    • yt-dlp로 트레일러 다운로드 (30초~5분, max 50MB)
    • 체크포인트: data/crawl_status.json
    • 출력: trailers/*.webm
    │
    ▼
[PLAN_02] batch_embed.py
    • OpenCV로 10프레임 균등 추출
    • CLIP ViT-B/32 → 512차원 float32 벡터
    • 10프레임 평균 → 영상 1개 = 벡터 1개
    • 배치 100개씩 pkl 저장
    • 팀원 제출용 parquet 출력 (vod_id + embedding)
    │
    ▼
[PLAN_03] ingest_to_db.py
    • pkl 파일 읽기 → VPC DB 적재
    • ON CONFLICT DO UPDATE (멱등성)
    • 시리즈 전파: 대표 에피소드 임베딩 → 전 에피소드 복사
    • 적재 후 IVF_FLAT 인덱스 생성
    ▼
[vod_embedding 테이블]
```

---

## 3. 스크립트별 핵심 로직

### 3-1. `crawl_trailers.py` (PLAN_01 — YouTube 수집)

**목적**: DB `vod` 테이블 → YouTube 검색 → `.webm` 다운로드

| 함수 | 역할 |
|------|------|
| `normalize_title()` | 숫자-한글 경계에 공백 삽입 → 검색 친화성 개선 |
| `strip_episode_suffix()` | "황제의 딸 1 01회" → "황제의 딸 1" 에피소드 suffix 제거 |
| `effective_series_nm()` | 오염된 series_nm 감지 후 asset_nm 기반 키로 대체 |
| `dedup_by_series_nm()` | 시리즈 기준 대표 1개만 유지 (중복 수집 방지) |
| `build_search_queries()` | 장르별 YouTube 검색 쿼리 3개 생성 (fallback 포함) |
| `duration_filter()` | 30초~5분 필터 (yt-dlp 훅) |
| `stratified_sample()` | ct_cl 계층별 층화 샘플 추출 |

**핵심 설정**:
```python
EXCLUDE_CT_CL        = {'우리동네', '미분류'}       # 크롤링 제외 유형
SERIES_EMBED_CT_CL   = {'TV드라마', 'TV 시사/교양', 'TV애니메이션', '키즈', '영화'}
EPISODE_EMBED_CT_CL  = {'TV 연예/오락'}              # 에피소드별 개별 임베딩
REQUEST_DELAY        = 1.5 ~ 3.0초                   # YouTube 차단 방지
DURATION_MIN/MAX     = 30 / 300초
```

**체크포인트**: `data/crawl_status.json`
```json
{
  "VOD001234": {
    "status": "done",
    "filename": "dQw4w9WgXcQ.webm",
    "query_used": "어바웃 타임 예고편",
    "ct_cl": "영화",
    "series_nm": null,
    "series_key": "어바웃 타임",
    "series_nm_is_bad": false
  }
}
```

---

### 3-2. `batch_embed.py` (PLAN_02 — CLIP 임베딩)

**목적**: `trailers/*.webm` → CLIP ViT-B/32 → `data/*.pkl`

| 함수 | 역할 |
|------|------|
| `load_clip_model()` | 로컬 경로 또는 HuggingFace에서 CLIP 로드 |
| `extract_frames()` | OpenCV로 N_FRAMES=10개 균등 추출 |
| `get_video_embedding()` | 프레임별 임베딩 → 평균 → 512차원 float32 |
| `check_vector_quality()` | magnitude 0.01~100.0 범위 품질 확인 |
| `save_batch()` | 100개 단위 pkl 저장 |
| `save_parquet()` | 팀원 제출용 parquet (vod_id + embedding list) |

**pkl 출력 포맷**:
```python
{
  "vod_id":     "VOD001234",
  "title":      "어바웃 타임",
  "video_file": "dQw4w9WgXcQ.webm",
  "vector":     np.array([...], dtype=np.float32),  # shape (512,)
  "magnitude":  float,
  "embedded_at": "2026-03-08T14:32:00",
  "ct_cl":      "영화",
  "series_nm":  None
}
```

**parquet 제출 전 검증 3종**:
1. `embedding` 길이 == 512
2. `vod_id` 중복 없음
3. NULL 없음

**핵심 설정**:
```python
BATCH_SIZE   = 100
N_FRAMES     = 10
MODEL_PATH   = "C:/Users/daewo/DX_prod_2nd/my_clip_model"  # 로컬 우선
MODEL_FALLBACK = "clip-ViT-B-32"                             # HuggingFace fallback
```

---

### 3-3. `ingest_to_db.py` (PLAN_03 — DB 적재)

**목적**: `data/*.pkl` → `vod_embedding` 테이블 삽입

| 함수 | 역할 |
|------|------|
| `ensure_table()` | vod_embedding 테이블 없으면 자동 생성 |
| `ingest_batch_file()` | pkl → DB INSERT (ON CONFLICT DO UPDATE) |
| `propagate_series_embeddings()` | 대표 임베딩 → 시리즈 전체 에피소드 복사 |
| `create_index_after_ingest()` | IVF_FLAT 코사인 인덱스 생성 |
| `run_verify()` | 적재 건수·커버리지·이상 벡터 검증 |

**시리즈 전파 전략**:
```
series_nm_is_bad = False  →  WHERE series_nm = %s AND ct_cl = %s   (exact match)
series_nm_is_bad = True   →  WHERE ct_cl = %s AND asset_nm LIKE %s  (LIKE 패턴)
```

**핵심 설정**:
```python
COMMIT_INTERVAL  = 1000
EMBEDDING_TYPE   = "VISUAL"
EMBEDDING_DIM    = 512
FRAME_COUNT      = 10
SOURCE_TYPE      = "TRAILER"
```

---

## 4. 파일럿 실행 결과 (2026-03-08 기준)

**대상**: ct_cl 층화 샘플 100건

| 단계 | 결과 | 소요 시간 |
|------|------|----------|
| PLAN_01 크롤링 | **98/100 성공 (98%)** | 11분 |
| PLAN_02 임베딩 | **78/98 성공 (79.6%)** | 1분 6초 |
| PLAN_03 적재 | **78/78 삽입, 오류 0건** | 1초 미만 |

**실패 20건 원인**: `--delete-after-embed` 옵션 사용 중 같은 YouTube 영상을 여러 vod_id가 공유하는 경우, 첫 번째 임베딩 직후 파일 삭제 → 나머지 vod_id 처리 실패

### 파일럿 중 발견·수정된 버그 4건

| 번호 | 버그 | 수정 내용 |
|------|------|----------|
| #1 | 층화 샘플에 동일 시리즈 중복 포함 | `dedup_by_series_nm()` 추가 |
| #2 | 에피소드 suffix 미처리 (공백 없는 케이스) | regex `\s+` → `\s*` |
| #3 | 숫자-한글 붙여쓰기로 YouTube 검색 실패 | `normalize_title()` 추가 |
| #4 | `duration_filter`가 모든 영상 차단 | `if incomplete: return None` 추가 |

---

## 5. Full 운영 시 개선 예정 사항

| 우선순위 | 항목 | 내용 |
|---------|------|------|
| P0 | 파일 공유 충돌 해결 | 같은 YouTube URL을 참조하는 vod_id 그룹화 후 한 번만 임베딩 + 복사 |
| P1 | YouTube 미등재 fallback | CLIP 텍스트 임베딩 또는 KMDb 포스터 이미지 임베딩 |
| P2 | 크롤링 병렬화 | ct_cl별 프로세스 분리 → 409 응답 적응형 딜레이 → 시리즈 레벨 dedup |

---

## 6. 예상 Full 운영 소요 시간

| 단계 | CPU 기준 | GPU 기준 |
|------|---------|---------|
| PLAN_01 크롤링 (~45K VOD) | 2~3일 (56시간) | 동일 (I/O 병목) |
| PLAN_02 임베딩 (~38K 대상) | 33~47시간 (10~15개/분) | 약 6분 (100개/분) |
| PLAN_03 적재 | 수 분 | 동일 |
| **합계** | **약 4~5일** | **약 2~3일** |

> 목표 커버리지: 전체 45K 중 **70% 이상 (31,500건+)**

---

## 7. TDD 에이전트 구조 (agents/)

7개 에이전트가 TDD 사이클로 코드를 개발·검증:

```
ORCHESTRATOR
    │  Phase 분해 및 전체 조율
    ├─ SECURITY_AUDITOR  ← 시작 전 / 커밋 전 보안 점검
    ├─ TEST_WRITER        ← 테스트 먼저 작성 (Red)
    ├─ DEVELOPER          ← 테스트 통과 구현 (Green)
    ├─ TESTER             ← 실제 테스트 실행
    ├─ REFACTOR           ← 코드 품질 개선 (Refactor)
    └─ REPORTER           ← Phase 결과 보고서 생성
```

---

## 8. 현재 상태 및 다음 단계

| 항목 | 상태 |
|------|------|
| 파이프라인 설계 (PLAN 00~03) | **완료** |
| 파일럿 100건 검증 | **완료** (버그 4건 수정) |
| Full 운영 (45K) | **미시작** |
| `src/` 모듈화 | **미시작** |
| `config/` 설정 파일 | **미시작** |
| GPU 서버 병렬 크롤링 | **미시작** |

### 즉시 착수 가능한 작업

1. **Full 크롤링 시작**: `python scripts/crawl_trailers.py --sample 45000`
2. **파일 공유 충돌 수정**: crawl_status.json에서 same-url 그룹 선처리 로직 추가
3. **rag_confidence 저장 연동**: RAG 브랜치에서 신뢰도 점수 기록 누락 수정 (별도 브랜치)

---

*분석 기준 파일: `VOD_Embedding/docs/reports/report.md`, `scripts/*.py`, `docs/plans/*.md`*
