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
| `public.detected_object_yolo` | `Object_Detection` | `Shopping_Ad`(읽기) |
| `public.detected_object_clip` | `Object_Detection` | `Shopping_Ad`(읽기) |
| `public.detected_object_stt` | `Object_Detection` | `Shopping_Ad`(읽기) |
| `public.seasonal_market` | `Shopping_Ad` | `Shopping_Ad`(읽기) |
| `public.vod_tag` | `Database_Design`(초기 적재) | `Hybrid_Layer`(읽기) |
| `public.user_preference` | `Hybrid_Layer` | `Hybrid_Layer`(읽기), `API_Server`(읽기) |
| `public.wishlist` | `API_Server` | `API_Server`(읽기/쓰기) |
| `public.episode_progress` | `API_Server` | `API_Server`(읽기/쓰기) |
| `public.purchase_history` | `API_Server` | `API_Server`(읽기/쓰기) |
| `public.point_history` | `API_Server` | `API_Server`(읽기/쓰기) |
| `public.watch_reservation` | `API_Server` | `API_Server`(읽기/쓰기) |
| `public.notifications` | `API_Server`, DB 트리거(`fn_notify_new_episode`) | `API_Server`(읽기/쓰기) |

### Gold 계층 (serving 스키마)

| 테이블/MV | 생산 브랜치 | 소비 브랜치 |
|-----------|------------|------------|
| `serving.vod_recommendation` | `CF_Engine`, `Vector_Search` | `Hybrid_Layer`(읽기), `API_Server`(읽기) |
| `serving.mv_vod_watch_stats` | `Database_Design`(cron REFRESH) | `API_Server`(읽기) |
| `serving.mv_age_grp_vod_stats` | `Database_Design`(cron REFRESH) | `API_Server`(읽기) |
| `serving.mv_daily_watch_stats` | `Database_Design`(cron REFRESH) | `API_Server`(읽기) |
| `serving.shopping_ad` | `Shopping_Ad` | `API_Server`(읽기) |
| `serving.popular_recommendation` | `CF_Engine`, `Vector_Search` | `API_Server`(읽기) |
| `serving.hybrid_recommendation` | `Hybrid_Layer` | `API_Server`(읽기) |
| `serving.tag_recommendation` | `Hybrid_Layer` | `API_Server`(읽기) |

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
| 쓰기 | `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | - | `'COLLABORATIVE'`, UNIQUE(user_id_fk, vod_id_fk, recommendation_type) |
| 쓰기 | `serving.popular_recommendation` | `ct_cl`, `rank`, `vod_id_fk`, `score`, `recommendation_type` | VARCHAR(64)/SMALLINT/VARCHAR(64)/REAL/VARCHAR(32) | `'POPULAR'` CT_CL별 Top-N |

### Vector_Search *(미구현)*

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.vod_embedding` | `vod_id_fk`, `embedding` | VECTOR(512) | 콘텐츠 유사도 검색 |
| 읽기 | `public.vod_meta_embedding` | `vod_id_fk`, `embedding` | VECTOR(384) | |
| 읽기 | `public.user_embedding` | `user_id_fk`, `embedding` | VECTOR(896) | 개인화 검색 |
| 쓰기 | `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | - | 유저 기반: `'VISUAL_SIMILARITY'`, UNIQUE(user_id_fk, vod_id_fk, recommendation_type) |
| 쓰기 | `serving.vod_recommendation` | `source_vod_id`, `vod_id_fk`, `rank`, `score`, `recommendation_type` | VARCHAR(64)/VARCHAR(64)/SMALLINT/REAL/VARCHAR(32) | 콘텐츠 기반: `'CONTENT_BASED'` |
| 쓰기 | `serving.popular_recommendation` | `ct_cl`, `rank`, `vod_id_fk`, `score`, `recommendation_type` | VARCHAR(64)/SMALLINT/VARCHAR(64)/REAL/VARCHAR(32) | `'POPULAR'` CT_CL별 Top-N |

### Hybrid_Layer

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `score`, `recommendation_type` | - | CF top 20 + Vector top 20 후보 |
| 읽기 | `public.vod_tag` | `vod_id_fk`, `tag_category`, `tag_value`, `confidence` | VARCHAR/VARCHAR/VARCHAR/REAL | 후보 VOD 태그 조회 |
| 읽기 | `public.user_preference` | `user_id_fk`, `tag_category`, `tag_value`, `affinity` | VARCHAR/VARCHAR/VARCHAR/REAL | 유저 선호 태그 조회 |
| 읽기 | `public.watch_history` | `user_id_fk`, `vod_id_fk`, `completion_rate` | - | user_preference 집계 입력 |
| 쓰기 | `public.user_preference` | `user_id_fk`, `tag_category`, `tag_value`, `affinity`, `watch_count`, `avg_completion` | - | ON CONFLICT UPSERT |
| 쓰기 | `serving.hybrid_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `explanation_tags`, `source_engines` | - | 최종 설명 가능 추천 |
| 쓰기 | `serving.tag_recommendation` | `user_id_fk`, `tag_category`, `tag_value`, `tag_rank`, `tag_affinity`, `vod_id_fk`, `vod_rank`, `vod_score` | - | 선호 태그별 VOD 선반 (top 5 × top 10) |

### Object_Detection

| 방향 | 테이블/파일 | 컬럼 | 타입 | 비고 |
|------|------------|------|------|------|
| 읽기 | 로컬 VOD 영상 파일 | `file_path`, `vod_id` | str | 추론 입력 |
| 읽기 | `public.vod` | `full_asset_id`, `youtube_video_id`, `duration_sec`, `trailer_processed` | VARCHAR(64)/VARCHAR(20)/REAL/BOOLEAN | VOD 식별 + 트레일러 상태 |
| 쓰기 | `data/vod_detected_object.parquet` (로컬) | `vod_id`, `frame_ts`, `label`, `confidence`, `bbox` | str/float/str/float/list | Shopping_Ad 소비 |
| 쓰기 | `data/vod_clip_concept.parquet` (로컬) | `vod_id`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | str/float/str/float/str/bool | Shopping_Ad 소비 |
| 쓰기 | `data/vod_stt_concept.parquet` (로컬) | `vod_id`, `start_ts`, `end_ts`, `transcript`, `keyword`, `ad_category`, `ad_hints` | str/float/float/str/str/str/list | Shopping_Ad 소비 |
| 쓰기 | `public.detected_object_yolo` | `vod_id_fk`, `frame_ts`, `label`, `confidence`, `bbox` | VARCHAR(64)/REAL/VARCHAR(64)/REAL/REAL[] | YOLO bbox 탐지 결과 |
| 쓰기 | `public.detected_object_clip` | `vod_id_fk`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid`, `context_reason` | VARCHAR(64)/REAL/VARCHAR(200)/REAL/VARCHAR(32)/BOOLEAN/TEXT | CLIP 개념 태깅 |
| 쓰기 | `public.detected_object_stt` | `vod_id_fk`, `start_ts`, `end_ts`, `transcript`, `keyword`, `ad_category`, `ad_hints` | VARCHAR(64)/REAL/REAL/TEXT/VARCHAR(100)/VARCHAR(32)/TEXT | STT 키워드 추출 |
| 쓰기 | `public.vod` | `trailer_processed` | BOOLEAN | 처리 완료 시 TRUE 갱신 |

### Shopping_Ad

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.detected_object_yolo` | `vod_id_fk`, `frame_ts`, `label`, `confidence`, `bbox` | VARCHAR(64)/REAL/VARCHAR(64)/REAL/REAL[] | YOLO 탐지 결과 |
| 읽기 | `public.detected_object_clip` | `vod_id_fk`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | VARCHAR(64)/REAL/VARCHAR(200)/REAL/VARCHAR(32)/BOOLEAN | CLIP 개념 태깅 |
| 읽기 | `public.detected_object_stt` | `vod_id_fk`, `start_ts`, `end_ts`, `keyword`, `ad_category`, `ad_hints` | VARCHAR(64)/REAL/REAL/VARCHAR(100)/VARCHAR(32)/TEXT | STT 키워드 |
| 읽기 | `public.vod` | `full_asset_id`, `asset_nm` | VARCHAR(64)/VARCHAR(255) | VOD 메타데이터 |
| 읽기 | `public.seasonal_market` | `product_name`, `broadcast_date`, `start_time`, `end_time`, `channel` | VARCHAR(200)/DATE/TIME/TIME/VARCHAR(32) | 제철장터 편성 매칭 |
| 쓰기 | `public.seasonal_market` | `product_name`, `broadcast_date`, `start_time`, `end_time`, `channel` | 각종 | 제철장터 편성 크롤링 적재 |
| 쓰기 | `serving.shopping_ad` | `vod_id_fk`, `ts_start`, `ts_end`, `ad_category`, `signal_source`, `score`, `ad_hints`, `ad_action_type`, `ad_image_url`, `product_name`, `channel` | 각종 | 광고 서빙 (지자체 팝업 + 제철장터 연계) |

### API_Server

| 방향 | 테이블 | 컬럼 | 타입 | 비고 |
|------|--------|------|------|------|
| 읽기 | `public.vod` | `full_asset_id`, `asset_nm`, `genre`, `ct_cl`, `director`, `cast_lead`, `smry`, `poster_url`, `release_date`, `rating`, `series_nm`, `asset_prod` | 각종 VARCHAR/TEXT | VOD 상세/시리즈 조회. `release_date` → `release_year`(연도 int) 변환. `asset_prod='FOD'` → `is_free=true`. `series_nm` 커버링 인덱스 활용 |
| 읽기 | `public."user"` | `sha2_hash` | VARCHAR | 사용자 존재 여부 확인 (PK) |
| 읽기 | `serving.vod_recommendation` | `user_id_fk`, `vod_id_fk`, `rank`, `score`, `recommendation_type`, `expires_at` | VARCHAR/REAL/TIMESTAMPTZ | `/recommend/{user_id}` — `WHERE recommendation_type = 'HYBRID'`, UNIQUE(user_id_fk, vod_id_fk, recommendation_type) |
| 읽기 | `serving.vod_recommendation` | `source_vod_id`, `vod_id_fk`, `rank`, `score`, `recommendation_type`, `expires_at` | VARCHAR/REAL/TIMESTAMPTZ | `/similar/{asset_id}` — `WHERE source_vod_id = $1 AND recommendation_type = 'CONTENT_BASED'` |
| 읽기 | `serving.popular_recommendation` | `ct_cl`, `rank`, `vod_id_fk`, `score`, `recommendation_type`, `expires_at` | VARCHAR(64)/SMALLINT/REAL/VARCHAR(32)/TIMESTAMPTZ | CT_CL별 인기 추천 Top-N |
| 읽기 | `serving.shopping_ad` | `vod_id_fk`, `ts_start`, `ts_end`, `ad_category`, `score`, `ad_hints`, `product_name`, `product_price`, `product_url`, `image_url`, `channel` | 각종 | 쇼핑 광고 팝업 서빙 |
| 읽기 | `serving.mv_vod_watch_stats` | *(스키마 확인 필요)* | - | 인기 콘텐츠 배너 |
| 읽기 | `serving.mv_age_grp_vod_stats` | *(스키마 확인 필요)* | - | 연령대별 추천 |
| 읽기 | `serving.mv_daily_watch_stats` | *(스키마 확인 필요)* | - | 통계 대시보드 |
| 읽기/쓰기 | `public.wishlist` | `user_id_fk`, `series_nm`, `created_at` | VARCHAR(64)/VARCHAR(255)/TIMESTAMPTZ | 찜 추가/해제/목록 조회. PK=(user_id_fk, series_nm) |
| 읽기/쓰기 | `public.episode_progress` | `user_id_fk`, `vod_id_fk`, `series_nm`, `completion_rate`, `watched_at` | VARCHAR(64)/VARCHAR(64)/VARCHAR(255)/SMALLINT/TIMESTAMPTZ | 에피소드 진행률. PK=(user_id_fk, vod_id_fk). ON CONFLICT UPDATE |
| 읽기/쓰기 | `public.purchase_history` | `purchase_id`, `user_id_fk`, `series_nm`, `option_type`, `points_used`, `purchased_at`, `expires_at` | BIGINT/VARCHAR(64)/VARCHAR(255)/VARCHAR(16)/INTEGER/TIMESTAMPTZ/TIMESTAMPTZ | 구매/대여 기록 |
| 읽기/쓰기 | `public.point_history` | `point_history_id`, `user_id_fk`, `type`, `amount`, `description`, `related_purchase_id`, `created_at` | BIGINT/VARCHAR(64)/VARCHAR(8)/INTEGER/VARCHAR(256)/BIGINT/TIMESTAMPTZ | 포인트 적립/사용. DB 트리거가 `user.point_balance` 자동 갱신 + `NOTIFY user_activity` |
| 읽기 | `public."user"` | `point_balance` | INTEGER | 포인트 잔액 O(1) 조회 (DB 트리거 자동 갱신) |
| 읽기/쓰기 | `public.watch_reservation` | `reservation_id`, `user_id_fk`, `channel`, `program_name`, `alert_at`, `notified` | SERIAL/VARCHAR(64)/INTEGER/VARCHAR(255)/TIMESTAMPTZ/BOOLEAN | 시청예약 등록/조회/삭제. 30초 주기 background task가 `notified` 갱신 |
| 읽기/쓰기 | `public.notifications` | `notification_id`, `user_id_fk`, `type`, `title`, `message`, `image_url`, `read`, `created_at` | SERIAL/VARCHAR(64)/VARCHAR(32)/VARCHAR(255)/VARCHAR(512)/TEXT/BOOLEAN/TIMESTAMPTZ | GNB 알림 벨. type: new_episode/reservation/system. 읽음/삭제 관리 |

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
