# 브랜치 의존성 지도 (Dependency Map)

**관리 브랜치**: `Database_Design`
**최초 작성**: 2026-03-12
**목적**: 마이그레이션 추가 시 공지 대상 브랜치를 기계적으로 판단하는 단일 참조 문서.
새 브랜치 생성 시 이 파일에 먼저 등록한다 (Rule 4).

---

## 테이블별 생산·소비 브랜치

### Silver 계층 (public 스키마)

| 테이블 | 생산 브랜치 | 소비 브랜치 |
|--------|------------|------------|
| `public.vod` | *(초기 데이터 적재)* | `RAG`(쓰기), `Poster_Collection`(쓰기), `VOD_Embedding`(읽기), `API_Server`(읽기) |
| `public."user"` | *(초기 데이터 적재)* | `User_Embedding`(읽기), `API_Server`(읽기) |
| `public.watch_history` | *(초기 데이터 적재)* | `User_Embedding`(읽기), `CF_Engine`(읽기) |
| `public.vod_embedding` | `VOD_Embedding` | `User_Embedding`(읽기), `Vector_Search`(읽기), `CF_Engine`(읽기) |
| `public.vod_meta_embedding` | `VOD_Embedding` | `User_Embedding`(읽기), `Vector_Search`(읽기) |
| `public.user_embedding` | `User_Embedding` | `CF_Engine`(읽기), `Vector_Search`(읽기) |
| `public.detected_objects` | `Object_Detection` | `Shopping_Ad`(읽기) |
| `public.tv_schedule` | *(외부 EPG 적재)* | `Shopping_Ad`(읽기) |

### Gold 계층 (serving 스키마)

| 테이블/MV | 생산 브랜치 | 소비 브랜치 |
|-----------|------------|------------|
| `serving.vod_recommendation` | `CF_Engine`, `Vector_Search` | `API_Server`(읽기) |
| `serving.mv_vod_watch_stats` | `Database_Design`(cron REFRESH) | `API_Server`(읽기) |
| `serving.mv_age_grp_vod_stats` | `Database_Design`(cron REFRESH) | `API_Server`(읽기) |
| `serving.mv_daily_watch_stats` | `Database_Design`(cron REFRESH) | `API_Server`(읽기) |

---

## 브랜치별 읽기/쓰기 컬럼 상세

### RAG

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.vod` | `full_asset_id` | VARCHAR(64) | 처리 대상 식별 |
| 읽기 | `public.vod` | `asset_nm`, `genre`, `ct_cl` | VARCHAR | RAG 검색 쿼리 생성용 |
| 읽기 | `public.vod` | `rag_processed` | BOOLEAN | FALSE인 레코드만 처리 |
| 쓰기 | `public.vod` | `director` | VARCHAR(255) | |
| 쓰기 | `public.vod` | `cast_lead` | TEXT | |
| 쓰기 | `public.vod` | `cast_guest` | TEXT | |
| 쓰기 | `public.vod` | `rating` | VARCHAR(16) | |
| 쓰기 | `public.vod` | `release_date` | DATE | |
| 쓰기 | `public.vod` | `smry` | TEXT | |
| 쓰기 | `public.vod` | `rag_processed` | BOOLEAN | 완료 시 TRUE |
| 쓰기 | `public.vod` | `rag_source` | VARCHAR(64) | TMDB/KMDB/JW 등 |
| 쓰기 | `public.vod` | `rag_processed_at` | TIMESTAMPTZ | |
| 쓰기 | `public.vod` | `rag_confidence` | REAL | 0.0~1.0 |

### Poster_Collection

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.vod` | `full_asset_id`, `series_nm` | VARCHAR | `poster_url IS NULL` 조건 |
| 쓰기 | `public.vod` | `poster_url` | TEXT | VPC 경로 또는 URL |

### VOD_Embedding

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.vod` | `full_asset_id`, `asset_nm`, `genre`, `director`, `cast_lead`, `smry` | 각종 | 메타 임베딩 입력 |
| 쓰기 | `public.vod_embedding` | `vod_id_fk` | VARCHAR(64) | UNIQUE |
| 쓰기 | `public.vod_embedding` | `embedding` | VECTOR(512) | CLIP ViT-B/32 |
| 쓰기 | `public.vod_embedding` | `embedding_type` | VARCHAR(32) | 허용값: `'CLIP'` |
| 쓰기 | `public.vod_embedding` | `model_name`, `model_version` | VARCHAR | `'clip-ViT-B-32'` |
| 쓰기 | `public.vod_embedding` | `frame_count` | SMALLINT | 기본 10 |
| 쓰기 | `public.vod_embedding` | `source_type` | VARCHAR(32) | 허용값: `'TRAILER'`,`'FULL'` |
| 쓰기 | `public.vod_meta_embedding` | `vod_id_fk` | VARCHAR(64) | UNIQUE |
| 쓰기 | `public.vod_meta_embedding` | `embedding` | VECTOR(384) | paraphrase-multilingual-MiniLM-L12-v2 |
| 쓰기 | `public.vod_meta_embedding` | `input_text` | TEXT | 결합 텍스트 (선택) |
| 쓰기 | `public.vod_meta_embedding` | `source_fields` | TEXT[] | 기본: `['asset_nm','genre','director','cast_lead','smry']` |

### User_Embedding

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.watch_history` | `user_id_fk`, `vod_id_fk`, `completion_rate` | VARCHAR/REAL | 가중 평균 가중치 |
| 읽기 | `public.vod_embedding` | `vod_id_fk`, `embedding` | VARCHAR/VECTOR(512) | CLIP 파트 |
| 읽기 | `public.vod_meta_embedding` | `vod_id_fk`, `embedding` | VARCHAR/VECTOR(384) | METADATA 파트 |
| 쓰기 | `public.user_embedding` | `user_id_fk` | VARCHAR(64) | ON CONFLICT 기준 (UNIQUE) |
| 쓰기 | `public.user_embedding` | `embedding` | VECTOR(896) | L2 정규화 후 concat |
| 쓰기 | `public.user_embedding` | `vod_count` | INTEGER | 임베딩 생성에 사용된 고유 VOD 수 |
| 쓰기 | `public.user_embedding` | `model_name` | VARCHAR(100) | `'weighted_mean'` |

### CF_Engine *(미구현)*

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.user_embedding` | `user_id_fk`, `embedding` | VARCHAR/VECTOR(896) | ALS 초기값 |
| 읽기 | `public.watch_history` | `user_id_fk`, `vod_id_fk`, `satisfaction` | - | 행렬 분해 입력 |
| 쓰기 | `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | - | `'COLLABORATIVE'` |

### Vector_Search *(미구현)*

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.vod_embedding` | `vod_id_fk`, `embedding` | VECTOR(512) | 콘텐츠 유사도 검색 |
| 읽기 | `public.vod_meta_embedding` | `vod_id_fk`, `embedding` | VECTOR(384) | |
| 읽기 | `public.user_embedding` | `user_id_fk`, `embedding` | VECTOR(896) | 개인화 검색 |
| 쓰기 | `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | - | 유저 기반: `'VISUAL_SIMILARITY'` |
| 쓰기 | `serving.vod_recommendation` | `source_vod_id`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | VARCHAR(64)/VARCHAR(64)/SMALLINT/REAL/VARCHAR(32) | 콘텐츠 기반: `'CONTENT_BASED'` |

### Object_Detection

| 방향 | 테이블/파일 | 컬럼 | 타입 | 비고 |
|------|------------|------|------|------|
| 읽기 | 로컬 VOD 영상 파일 | `file_path`, `vod_id` | str | 추론 입력 |
| 읽기 | `public.vod` | `full_asset_id` | VARCHAR(64) | VOD 식별자 매핑 (선택) |
| 쓰기 | `data/vod_detected_object.parquet` (로컬) | `vod_id` | str | Shopping_Ad 소비 |
| 쓰기 | `data/vod_detected_object.parquet` (로컬) | `frame_ts` | float | 프레임 타임스탬프(초) |
| 쓰기 | `data/vod_detected_object.parquet` (로컬) | `label` | str | YOLO COCO 클래스명 |
| 쓰기 | `data/vod_detected_object.parquet` (로컬) | `confidence` | float | 0.5 이상만 저장 |
| 쓰기 | `data/vod_detected_object.parquet` (로컬) | `bbox` | list[float] | [x1,y1,x2,y2] 픽셀 좌표 |
| 쓰기 | `public.detected_objects` (VPC — 예정) | *(스키마 미확정)* | - | Database_Design과 협의 후 확정 |

### Shopping_Ad *(미구현)*

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.detected_objects` | *(스키마 미확정)* | - | |
| 읽기 | `public.tv_schedule` | *(스키마 미확정)* | - | |

### API_Server

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.vod` | `full_asset_id`, `asset_nm`, `genre`, `director`, `cast_lead`, `smry`, `poster_url`, `release_date`, `rating` | 각종 VARCHAR/TEXT | `/vod/{asset_id}` 상세 응답 |
| 읽기 | `public."user"` | `sha2_hash` | VARCHAR | 사용자 존재 여부 확인 (PK) |
| 읽기 | `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | VARCHAR/REAL | `/recommend/{user_id}` |
| 읽기 | `serving.mv_vod_watch_stats` | *(스키마 확인 필요)* | - | 인기 콘텐츠 배너 |
| 읽기 | `serving.mv_age_grp_vod_stats` | *(스키마 확인 필요)* | - | 연령대별 추천 |
| 읽기 | `serving.mv_daily_watch_stats` | *(스키마 확인 필요)* | - | 통계 대시보드 |

---

## 마이그레이션 영향 브랜치 조회 방법 (Rule 2 적용)

마이그레이션 추가 시 이 파일에서 변경 테이블을 찾아 **소비 브랜치**를 공지 대상으로 확정한다.

```
예시: vod_embedding 컬럼 변경
  → 위 테이블에서 vod_embedding 소비 브랜치 조회
  → User_Embedding, Vector_Search, CF_Engine 공지
  → 해당 브랜치 CLAUDE.md 인터페이스 섹션 동시 수정
```

---

## 새 브랜치 등록 절차 (Rule 4)

새 브랜치를 생성하면 **첫 커밋 전에** 이 파일을 수정한다.

1. 읽는 테이블 → 해당 행의 "소비 브랜치"에 추가
2. 쓰는 테이블 → 해당 행의 "생산 브랜치"에 추가
3. 새 테이블 필요 시 → `Database_Design`과 협의 후 행 추가
4. 브랜치별 컬럼 상세 섹션에 상세 명세 추가

**등록 없이 DB 연동 코드 작성 금지.**
