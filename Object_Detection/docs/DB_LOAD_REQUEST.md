# DB 적재 요청 (조장님)

**작성일**: 2026-03-23
**요청자**: 박아름 (Object_Detection + Shopping_Ad)

---

## 1. VOD 신규 등록 (19건)

아래 19건의 VOD를 `public.vod` 테이블에 등록해주세요.
youtube_video_id와 영상 제목을 드리니, 조장님이 크롤링해서 메타데이터(smry 등) 채워주시면 됩니다.

### 여행 — 동원아 여행가자

| file_id | asset_nm | genre_detail | primary_location | youtube_video_id |
|---------|----------|-------------|-----------------|-----------------|
| travel_dongwon_06 | 동원아 여행가자 06회 | 여행 | 영월 | fUDjJKcacdU |
| travel_dongwon_11 | 동원아 여행가자 11회 | 여행 | 정선 | sQEhu9y29qQ |
| travel_dongwon_12 | 동원아 여행가자 12회 | 여행 | 삼척 | 8Q2kdaToxk0 |
| travel_dongwon_15 | 동원아 여행가자 15회 | 여행 | 태백 | pyraZGbe4y0 |
| travel_dongwon_16 | 동원아 여행가자 16회 | 여행 | 제주 | KGjxaD-rdg0 |

### 여행 — 서울촌놈

| file_id | asset_nm | genre_detail | primary_location | youtube_video_id |
|---------|----------|-------------|-----------------|-----------------|
| travel_chonnom_01 | 서울촌놈 01회 | 여행 | 부산 | fqtBOF8kJrQ |
| travel_chonnom_03 | 서울촌놈 03회 | 여행 | 광주 | mQXHy_ScL5I |
| travel_chonnom_05 | 서울촌놈 05회 | 여행 | 청주 | kcJuGQAGJGA |
| travel_chonnom_07 | 서울촌놈 07회 | 여행 | 대전 | DNwH-NQGS-U |
| travel_chonnom_09 | 서울촌놈 09회 | 여행 | 전주 | WLNlIm6UMm0 |

### 음식 — 알토란

| file_id | asset_nm | genre_detail | primary_location | youtube_video_id |
|---------|----------|-------------|-----------------|-----------------|
| food_altoran_418 | 알토란 418회 | 음식_먹방 | - | nz3ZeYyBVSQ |
| food_altoran_440 | 알토란 440회 | 음식_먹방 | - | gjbXH09tZSw |
| food_altoran_490 | 알토란 490회 | 음식_먹방 | - | YkFCNmqNg4k |
| food_altoran_496 | 알토란 496회 | 음식_먹방 | - | O2QvRLsNcrQ |

### 음식 — 로컬식탁 (네이버 영상)

| file_id | asset_nm | genre_detail | primary_location | youtube_video_id |
|---------|----------|-------------|-----------------|-----------------|
| food_local_dakgalbi | 로컬식탁 춘천 닭갈비 | 음식_먹방 | 춘천 | - (네이버) |
| food_local_keyjo | 로컬식탁 보령 키조개 | 음식_먹방 | 보령 | - (네이버) |
| food_local_memill | 로컬식탁 강원 메밀 막국수 | 음식_먹방 | 강원 | - (네이버) |
| food_local_samchi | 로컬식탁 삼치회 | 음식_먹방 | 여수 | - (네이버) |
| food_local_sugyuk | 로컬식탁 원산도 수육국수 | 음식_먹방 | 보령 | - (네이버) |

> **ct_cl**: 전부 "TV 연예/오락"
> **series_nm**: 동원아 여행가자 / 서울촌놈 / 알토란 / 로컬식탁

### 등록 후 필요 사항
- 각 VOD에 `full_asset_id` 부여
- `file_id → full_asset_id` 매핑 알려주세요 (parquet의 vod_id 치환용)
- `smry` 크롤링 채워주시면 지역 1차 필터링에 활용합니다

---

## 2. DDL 실행 요청

### detected_object_ocr (신규)

```sql
CREATE TABLE detected_object_ocr (
    detected_ocr_id  BIGINT       GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk        VARCHAR(64)  NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    frame_ts         REAL         NOT NULL,
    detected_text    VARCHAR(300) NOT NULL,
    confidence       REAL         NOT NULL,
    bbox             REAL[]       NOT NULL,
    ad_category      VARCHAR(32),
    region_hint      VARCHAR(64),
    created_at       TIMESTAMPTZ  DEFAULT NOW(),
    CONSTRAINT chk_ocr_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT chk_ocr_bbox_len   CHECK (array_length(bbox, 1) = 4)
);
```

### vod_ad_summary (신규)

```sql
CREATE TABLE vod_ad_summary (
    vod_id_fk       VARCHAR(64)  PRIMARY KEY REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    ad_categories   TEXT[]       NOT NULL,
    primary_region  VARCHAR(64),
    ad_regions      TEXT[],
    trigger_count   SMALLINT     NOT NULL DEFAULT 0,
    top_keywords    TEXT[],
    created_at      TIMESTAMPTZ  DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  DEFAULT NOW()
);
```

### serving 스키마 + shopping_ad

- `Database_Design/schemas/create_shopping_ad_serving.sql` 실행
- `serving.shopping_ad.signal_source` CHECK에 `'ocr'` 추가 필요

---

## 3. parquet 파일 목록 (DB 적재용)

VOD 등록 + DDL 실행 후 적재할 파일들:

| 파일 | 위치 | 행수 | DB 테이블 |
|------|------|------|-----------|
| vod_detected_object.parquet | Object_Detection/data/parquet_output/ | 458 | detected_object_yolo |
| vod_clip_concept.parquet | 〃 | 3,519 | detected_object_clip |
| vod_stt_concept.parquet | 〃 | 620 | detected_object_stt |
| vod_ocr_concept.parquet | 〃 | 29,378 | detected_object_ocr |
| vod_ad_summary.parquet | Shopping_Ad/data/ | 19 | vod_ad_summary |
| shopping_ad_candidates.parquet | Shopping_Ad/data/ | 10 | serving.shopping_ad |

> parquet의 `vod_id`는 현재 file_id(travel_chonnom_09 등).
> VOD 등록 후 `full_asset_id` 매핑 받으면 치환 스크립트 실행합니다.

---

## 4. 일정

| 작업 | 기한 |
|------|------|
| VOD 19건 등록 + smry 크롤링 | 발표 전 |
| DDL 실행 (OCR + summary + serving) | 발표 전 |
| file_id → full_asset_id 매핑 전달 | VOD 등록 후 |
| parquet 적재 | 매핑 받은 후 |
| 제철장터 재크롤링 | 4/7~8 |
| 축제 재크롤링 | 4/7~8 |
