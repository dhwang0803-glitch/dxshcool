# VOD_Embedding Branch - Claude Code 작업 지침

**프로젝트**: VOD 추천 시스템 — VOD 임베딩 파이프라인
**담당**: 담당자 C (Phase 2-2)
**브랜치**: VOD_Embedding
**상태**: 진행 중

---

## 프로젝트 개요

### 목표
vod 테이블의 45,000개 VOD 전체에 대해 CLIP 임베딩 벡터를 생성하여
PostgreSQL vod_embedding 테이블(pgvector)에 적재.

### 전체 파이프라인
```
vod 테이블 (asset_nm, genre, ct_cl)
    ↓ [PLAN_01] YouTube 검색 + yt-dlp 다운로드
trailers/*.webm  (트레일러 영상)
    ↓ [PLAN_02] CLIP ViT-B/32 배치 임베딩
video_embs.pkl   (List[{vod_id, title, vector}])
    ↓ [PLAN_03] pgvector INSERT
vod_embedding 테이블 (VECTOR(512))
```

---

## 확정된 기술 스택

| 항목 | 결정 |
|------|------|
| 임베딩 모델 | CLIP ViT-B/32 (`sentence-transformers/clip-ViT-B-32`) |
| 벡터 차원 | 512차원 float32 |
| 벡터 DB | PostgreSQL + pgvector (VECTOR(512), IVF_FLAT lists=100) |
| 트레일러 수집 | yt-dlp (YouTube 검색 기반) |
| 프레임 추출 | OpenCV, 10프레임 균등 추출 후 평균 |
| Python 환경 | Anaconda myenv (torch, sentence-transformers 설치됨) |

---

## 주요 파일 경로

### 로컬 (작업 환경)
```
C:\Users\daewo\DX_prod_2nd\
├── my_clip_model\          # CLIP ViT-B/32 로컬 저장 모델
├── trailers\               # 다운로드된 트레일러 영상 (현재 5개)
├── video_embs.pkl          # 임베딩 결과 (현재 1개, 5개로 갱신 예정)
├── 202301_complete.parquet # 시청이력 원본 데이터
└── vector_embedding.ipynb  # 프로토타입 노트북 (파이프라인 참조용)
```

### 이 브랜치
```
VOD_Embedding/
├── .claude/claude_md.md    # 이 파일
├── plans/                  # 단계별 실행 계획
├── pipeline/               # 실행 스크립트
└── data/                   # 중간 결과물 (.gitignore 대상)
```

### Database_Design 브랜치 (참조)
```
Database_Design/
├── schema/create_embedding_tables.sql  # vod_embedding DDL (pgvector)
├── migration/vod_ingest_pipeline.py    # 신규 소량 VOD 추가용 (참조)
└── .env                                # VPC DB 접속 정보
```

---

## 핵심 설계 결정

### 1. YouTube 검색 쿼리 전략
- 기본: `{asset_nm} {year} 예고편` 또는 `{asset_nm} trailer official`
- 한국어 VOD: 한국어 제목으로 먼저 검색, 실패 시 영어 제목으로 fallback
- 신뢰도 기준: 영상 길이 30초~5분 (트레일러 범위)
- 실패 처리: 검색 실패 시 `trailer_found = FALSE`로 기록 후 스킵

### 2. 배치 처리 전략
- 45K VOD를 한 번에 처리하지 않고 배치(1,000개 단위)로 분할
- 체크포인트: 처리 완료된 vod_id를 별도 파일에 기록 → 재시작 시 이어서 처리
- 오류 격리: 개별 VOD 실패가 전체 배치를 중단하지 않음

### 3. full_asset_id 매핑
- 기존 VOD: vod 테이블의 `full_asset_id` 그대로 사용 (매핑 필요 없음)
- 신규 YouTube VOD: `"yt|{sha256(filename)[:16]}"` (vod_ingest_pipeline.py 방식)

### 4. 품질 관리
- `vector_magnitude`로 이상 벡터 감지 (0에 가깝거나 극단값)
- 프레임 추출 실패 시 해당 VOD 스킵 + 로그 기록
- 최종 적재율 목표: 45,000개 중 70% 이상 (트레일러 미존재 VOD 제외)

---

## 단계별 진행 상황

- [ ] PLAN_01: YouTube 검색 + 트레일러 다운로드
- [ ] PLAN_02: CLIP 배치 임베딩
- [ ] PLAN_03: vod_embedding DB 적재

---

## 참조 문서

- `Database_Design/plans/PLAN_04_EXTENSION_TABLES.md` — vod_embedding 스키마 설계
- `Database_Design/schema/create_embedding_tables.sql` — DDL
- `docs/COLLABORATION.md` — 전체 팀 역할 분담
- `VOD_Embedding/plans/PLAN_00_MASTER.md` — 이 브랜치 전체 계획
