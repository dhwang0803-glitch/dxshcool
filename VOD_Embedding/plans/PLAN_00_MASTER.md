# PLAN_00: VOD 임베딩 파이프라인 마스터 플랜

**브랜치**: VOD_Embedding
**담당**: 담당자 C (Phase 2-2)
**작성일**: 2026-03-08
**목표**: 45,000개 VOD 전체 CLIP 임베딩 → vod_embedding 테이블 적재

---

## 전체 구조

```
[PLAN_01] vod 테이블 → YouTube 검색 → 트레일러 다운로드 (trailers/)
                ↓
[PLAN_02] trailers/ → CLIP ViT-B/32 → video_embs_batch_*.pkl
                ↓
[PLAN_03] video_embs_batch_*.pkl → vod_embedding (PostgreSQL + pgvector)
```

---

## 단계별 요약

| 단계 | 파일 | 입력 | 출력 | 예상 시간 |
|------|------|------|------|---------|
| PLAN_01 | `pipeline/crawl_trailers.py` | vod 테이블 (45K) | `trailers/*.webm` | 수 시간~수일 |
| PLAN_02 | `pipeline/batch_embed.py` | `trailers/*.webm` | `data/video_embs_batch_*.pkl` | 수 시간 |
| PLAN_03 | `pipeline/ingest_to_db.py` | pkl 파일들 | `vod_embedding` 테이블 | 수 분 |

---

## 핵심 제약 및 전제

### 데이터 현황
- vod 테이블: 약 45,000개 VOD (`full_asset_id`, `asset_nm`, `genre`, `ct_cl` 등)
- 기존 임베딩: 5개 트레일러 테스트 완료 (vector_embedding.ipynb)
- 모델: CLIP ViT-B/32, 512차원, 로컬 저장 (`C:\Users\daewo\DX_prod_2nd\my_clip_model`)

### YouTube 검색 한계
- 45K VOD 중 트레일러 확보 가능 예상: **약 60~80%**
  - 오래된 콘텐츠, 국내 드라마/예능 등은 YouTube 트레일러 없을 수 있음
  - 키즈 콘텐츠, 홈쇼핑 채널: 트레일러 없음 (ct_cl로 필터링)
- YouTube 검색 API 없이 yt-dlp 사용 → 요청 속도 제한 필요 (초당 1~2건)

### VPC DB 연결
- vod 테이블 조회: VPC PostgreSQL (`.env` 접속 정보)
- vod_embedding INSERT: 동일 VPC (pgvector 확장 설치 후)

---

## 처리 제외 대상 (ct_cl 기준)

YouTube 트레일러를 기대하기 어려운 카테고리는 PLAN_01에서 사전 제외:

| ct_cl | 사유 | 처리 |
|-------|------|------|
| 홈쇼핑 | 상품 판매 영상 — 트레일러 없음 | 제외 |
| 키즈 | 국내 제작 단편 — 검색 불확실 | 조건부 포함 |
| 영화 | 공식 트레일러 존재 가능성 높음 | 포함 |
| 드라마 | 하이라이트 클립 검색 가능 | 포함 |
| 예능 | 방송 클립 검색 가능 | 포함 |

---

## 파일 구조

```
VOD_Embedding/
├── .claude/
│   └── claude_md.md
├── plans/
│   ├── PLAN_00_MASTER.md         ← 이 파일
│   ├── PLAN_01_TRAILER_CRAWL.md  ← YouTube 검색 + 다운로드
│   ├── PLAN_02_BATCH_EMBED.md    ← CLIP 배치 임베딩
│   └── PLAN_03_DB_INGEST.md      ← pgvector DB 적재
├── pipeline/
│   ├── crawl_trailers.py         ← PLAN_01 구현
│   ├── batch_embed.py            ← PLAN_02 구현
│   └── ingest_to_db.py          ← PLAN_03 구현
└── data/                         ← .gitignore (pkl, webm 등 대용량)
    ├── crawl_status.json         ← 다운로드 진행 상황 체크포인트
    ├── embed_status.json         ← 임베딩 진행 상황 체크포인트
    └── video_embs_batch_*.pkl    ← 배치별 임베딩 결과
```

---

## 진행 체크리스트

### PLAN_01: 트레일러 수집
- [ ] vod 테이블에서 대상 VOD 목록 추출 (ct_cl 필터 적용)
- [ ] `crawl_trailers.py` 실행 (배치, 체크포인트)
- [ ] 수집 결과 확인 (`crawl_status.json`)

### PLAN_02: 배치 임베딩
- [ ] `batch_embed.py` 실행
- [ ] 배치별 pkl 생성 확인

### PLAN_03: DB 적재
- [ ] VPC pgvector 확장 확인 (`CREATE EXTENSION vector`)
- [ ] vod_embedding 테이블 생성 확인 (create_embedding_tables.sql)
- [ ] `ingest_to_db.py` 실행
- [ ] 적재 건수 검증

---

**다음**: PLAN_01_TRAILER_CRAWL.md
