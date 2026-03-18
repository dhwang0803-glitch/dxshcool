# Shopping_Ad + Object_Detection 파이프라인 Flow

**작성일**: 2026-03-18
**상태**: 설계 검토 중 (Object_Detection 담당자 협의 후 DB 반영 예정)
**관련 브랜치**: `Database_Design`, `Object_Detection`, `Shopping_Ad`

---

## 1. 동작 흐름 (Operational Flow)

VOD 재생 중 쇼핑 팝업을 띄우기까지 3단계로 나뉜다.

### Phase A: 사전 배치 처리 (로컬, 1회)

Object_Detection 파이프라인이 트레일러 영상을 로컬에서 분석하고 결과를 VPC DB에 적재한다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase A: 사전 배치 처리 (로컬, 1회)                                         │
│                                                                             │
│  ┌──────────────┐    ┌─────────────────────────────────────────────────┐    │
│  │  public.vod   │    │         Object_Detection (로컬 GPU/CPU)        │    │
│  │               │    │                                                 │    │
│  │ youtube_video ├───►│  1) yt-dlp 다운로드                             │    │
│  │ _id           │    │  2) frame_extractor.py  (N fps 샘플링)          │    │
│  │ trailer_      │    │  3) detector.py         (YOLOv11 추론)         │    │
│  │ processed     │    │  4) clip_scorer.py      (CLIP zero-shot)       │    │
│  │ = FALSE       │    │  5) context_filter.py   (맥락 검증)            │    │
│  └───────────────┘    │  6) stt_scorer.py       (Whisper STT)          │    │
│                       └──────────┬──────────┬──────────┬───────────────┘    │
│                                  │          │          │                     │
│                                  ▼          ▼          ▼                    │
│                         .parquet(YOLO) .parquet(CLIP) .parquet(STT)         │
│                                  │          │          │                     │
│                                  ▼          ▼          ▼                    │
│                       ┌──────────────────────────────────────┐              │
│                       │   ingest_to_db.py  (VPC 적재)         │              │
│                       └──────────┬──────────┬────────┬───────┘              │
│                                  │          │        │                       │
│                                  ▼          ▼        ▼                      │
│                          detected_   detected_  detected_                   │
│                          object_     object_    object_                     │
│                          yolo        clip       stt                         │
│                                                                             │
│  trailer_processed = TRUE  ◄── UPDATE vod SET trailer_processed = TRUE     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**동작 상세:**

1. `public.vod`에서 `trailer_processed = FALSE`이고 `youtube_video_id IS NOT NULL`인 VOD 조회
2. `yt-dlp`로 트레일러 다운로드 → `frame_extractor.py`로 프레임 추출
3. 3종 분석 순차 실행:
   - **YOLO**: bbox 객체 탐지 → `vod_detected_object.parquet`
   - **CLIP**: zero-shot 개념 태깅 + context_filter 검증 → `vod_clip_concept.parquet`
   - **STT**: Whisper 전사 + 키워드 추출 → `vod_stt_concept.parquet`
4. `ingest_to_db.py`로 parquet → VPC 3개 테이블 적재
5. `trailer_processed = TRUE`로 갱신, 영상 파일 삭제 가능

### Phase B: 매일 자정 크론 (Shopping_Ad)

홈쇼핑 크롤링 + 탐지 결과 매칭으로 `serving.shopping_ad`를 갱신한다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase B: 매일 자정 크론 (Shopping_Ad)                                      │
│                                                                             │
│  ┌──────────────────┐     ┌──────────────────┐                              │
│  │ 홈쇼핑 사이트     │     │ EPG 소스          │                              │
│  │ (CJ온스타일 등)   │     │ (편성표 API)      │                              │
│  └────────┬─────────┘     └────────┬─────────┘                              │
│           │ 크롤링                  │ 크롤링                                  │
│           ▼                        ▼                                        │
│  ┌────────────────┐     ┌──────────────────┐                                │
│  │ homeshopping_  │     │   tv_schedule     │                                │
│  │ product        │     │                   │                                │
│  └────────┬───────┘     └────────┬─────────┘                                │
│           │                      │                                          │
│           └──────────┬───────────┘                                          │
│                      ▼                                                      │
│           ┌──────────────────────────────────────┐                          │
│           │   Shopping_Ad 매칭 엔진               │                          │
│           │                                       │                          │
│           │  1) detected_object_* 3종 조회        │                          │
│           │  2) ad_category별 트리거 구간 집계      │                          │
│           │  3) homeshopping_product 상품 매칭     │                          │
│           │  4) 비정규화 + score 계산              │                          │
│           └──────────────┬───────────────────────┘                          │
│                          ▼                                                  │
│              ┌───────────────────────┐                                      │
│              │  serving.shopping_ad   │                                      │
│              │  (TTL 30일)            │                                      │
│              └───────────────────────┘                                      │
└─────────────────────────────────────────────────────────────────────────────┘
```

**동작 상세:**

1. 홈쇼핑 사이트 크롤링 → `homeshopping_product` UPSERT
2. EPG 편성표 크롤링 → `tv_schedule` UPSERT
3. 매칭 엔진:
   - `detected_object_clip` / `detected_object_stt`에서 `ad_category`별 트리거 구간 집계
   - `detected_object_yolo`에서 보조 신호 추가 (음식/물건 bbox)
   - `homeshopping_product`에서 카테고리·시간대 기반 상품 매칭
   - 비정규화된 상품 정보와 함께 `serving.shopping_ad`에 INSERT
4. `expires_at` 30일 지난 레코드 정리

### Phase C: 실시간 서빙

UI가 영상 재생 중 `currentTime`을 폴링하여 API에서 팝업 데이터를 조회한다.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Phase C: 실시간 서빙                                                       │
│                                                                             │
│  ┌──────────┐  currentTime   ┌─────────────┐  SQL 쿼리  ┌────────────────┐ │
│  │ UI 영상   │ ──(0.5초)───► │  API_Server  │ ────────► │ serving.       │ │
│  │ 재생 중   │               │  /ad/popup   │           │ shopping_ad    │ │
│  │          │  ◄──팝업 JSON──│              │ ◄─결과──── │                │ │
│  └──────────┘               └─────────────┘           └────────────────┘ │
│                                                                             │
│  쿼리: SELECT * FROM serving.shopping_ad                                    │
│        WHERE vod_id_fk = $1                                                 │
│          AND ts_start <= $2 AND ts_end >= $2                                │
│          AND expires_at > NOW()                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**성능 포인트:**

- `serving.shopping_ad`에 상품 정보가 비정규화되어 있어 **JOIN 없이 단일 SELECT**로 응답
- 인덱스 `(vod_id_fk, ts_start, ts_end)`가 쿼리 패턴에 최적화

---

## 2. 데이터 흐름 (Data Flow)

로컬 영상 파일에서 UI 팝업까지 데이터가 어떤 테이블을 거쳐 흐르는지 보여준다.

```
                        ┌─────────────────────────────┐
                        │       로컬 VOD 영상 파일       │
                        │    (트레일러 5,726개)          │
                        └──────────────┬──────────────┘
                                       │
                          Object_Detection (로컬)
                    ┌──────────────────┼──────────────────┐
                    │                  │                   │
                    ▼                  ▼                   ▼
        ┌───────────────┐  ┌───────────────┐  ┌───────────────┐
        │  vod_detected  │  │  vod_clip      │  │  vod_stt      │
        │  _object       │  │  _concept      │  │  _concept     │
        │  .parquet      │  │  .parquet      │  │  .parquet     │
        │                │  │                │  │               │
        │ vod_id         │  │ vod_id         │  │ vod_id        │
        │ frame_ts       │  │ frame_ts       │  │ start_ts      │
        │ label          │  │ concept        │  │ end_ts        │
        │ confidence     │  │ clip_score     │  │ transcript    │
        │ bbox           │  │ ad_category    │  │ keyword       │
        │                │  │ context_valid  │  │ ad_category   │
        └───────┬───────┘  └───────┬───────┘  │ ad_hints      │
                │                  │           └───────┬───────┘
                │      ingest_to_db.py                 │
                ▼                  ▼                   ▼
 ═══════════════════════════ VPC PostgreSQL ════════════════════════════
 │                                                                     │
 │  ┌─ Silver 계층 (public) ─────────────────────────────────────────┐ │
 │  │                                                                 │ │
 │  │  ┌──────────────────┐                                           │ │
 │  │  │    public.vod     │◄──── youtube_video_id, duration_sec,     │ │
 │  │  │                   │      trailer_processed (마이그레이션)     │ │
 │  │  │  PK: full_asset   │                                           │ │
 │  │  │  _id              │                                           │ │
 │  │  └────────┬──────────┘                                           │ │
 │  │           │ FK (ON DELETE CASCADE)                                │ │
 │  │     ┌─────┼─────────────────┬───────────────────┐                │ │
 │  │     ▼                      ▼                    ▼                │ │
 │  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐           │ │
 │  │  │ detected_    │  │ detected_    │  │ detected_    │           │ │
 │  │  │ object_yolo  │  │ object_clip  │  │ object_stt   │           │ │
 │  │  │              │  │              │  │              │           │ │
 │  │  │ frame_ts     │  │ frame_ts     │  │ start_ts     │           │ │
 │  │  │ label        │  │ concept      │  │ end_ts       │           │ │
 │  │  │ confidence   │  │ clip_score   │  │ keyword      │           │ │
 │  │  │ bbox[]       │  │ ad_category  │  │ ad_category  │           │ │
 │  │  │              │  │ context_valid│  │ ad_hints     │           │ │
 │  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘           │ │
 │  │         │                 │                  │                   │ │
 │  │         └─────────────────┼──────────────────┘                   │ │
 │  │                           │ 읽기                                  │ │
 │  │                           ▼                                      │ │
 │  │              ┌─────────────────────────┐                         │ │
 │  │              │  Shopping_Ad 매칭 엔진   │◄─────────────┐         │ │
 │  │              └─────────────┬───────────┘              │         │ │
 │  │                            │                          │         │ │
 │  │  ┌──────────────┐         │        ┌────────────────┐│         │ │
 │  │  │  tv_schedule  │─읽기──►│◄─읽기──│ homeshopping_  ││         │ │
 │  │  │              │         │        │ product        ││         │ │
 │  │  │ channel      │         │        │                ││         │ │
 │  │  │ broadcast_   │         │        │ id ────────────┼┼─FK──┐  │ │
 │  │  │ date         │         │        │ normalized_name││     │  │ │
 │  │  │ start_time   │         │        │ price          ││     │  │ │
 │  │  │ program_name │         │        │ product_url    ││     │  │ │
 │  │  └──────────────┘         │        │ image_url      ││     │  │ │
 │  │                           │        └────────────────┘│     │  │ │
 │  └───────────────────────────┼──────────────────────────┘     │  │ │
 │                              │                                │  │ │
 │  ┌─ Gold 계층 (serving) ─────┼────────────────────────────────┼──┘ │
 │  │                           ▼                                │    │
 │  │  ┌──────────────────────────────────────────────────┐      │    │
 │  │  │          serving.shopping_ad                      │      │    │
 │  │  │                                                   │      │    │
 │  │  │  vod_id_fk ──FK──► public.vod                    │      │    │
 │  │  │  ts_start, ts_end       ← 트리거 구간 (초)        │      │    │
 │  │  │  ad_category            ← 한식/여행지/특산물       │      │    │
 │  │  │  signal_source          ← stt | clip | yolo      │      │    │
 │  │  │  score                  ← 0.0~1.0                │      │    │
 │  │  │  product_id_fk ─FK─────────────────────────────────┘    │
 │  │  │  product_name ┐                                         │    │
 │  │  │  product_price├─비정규화 (JOIN 없이 바로 응답)            │    │
 │  │  │  product_url  │                                         │    │
 │  │  │  image_url    ┘                                         │    │
 │  │  │  channel                ← 홈쇼핑 채널명                  │    │
 │  │  │  expires_at             ← TTL 30일                      │    │
 │  │  └──────────────────────────┬───────────────────────┘      │    │
 │  └─────────────────────────────┼──────────────────────────────┘    │
 │                                │                                    │
 ══════════════════════════════════╪════════════════════════════════════
                                  │ SELECT WHERE vod_id=$1
                                  │   AND ts_start<=$2 AND ts_end>=$2
                                  ▼
                        ┌──────────────────┐
                        │    API_Server     │
                        │  GET /ad/popup   │
                        └────────┬─────────┘
                                 │ JSON
                                 ▼
                        ┌──────────────────┐
                        │   Frontend UI     │
                        │  쇼핑 팝업 표시    │
                        └──────────────────┘
```

---

## 설계 핵심 포인트

### 3종 테이블 분리 (`detected_objects` → `yolo` / `clip` / `stt`)

| 결정 | 이유 |
|------|------|
| 모달리티별 분리 | YOLO(bbox), CLIP(개념+점수), STT(구간+키워드) 스키마가 근본적으로 다름 |
| write-once | 배치 적재 후 수정 없음 → `updated_at` 불필요, INSERT 성능 최적화 |
| FK CASCADE | VOD 삭제 시 탐지 결과 자동 정리 |

### 비정규화 (`serving.shopping_ad`)

| 결정 | 이유 |
|------|------|
| 상품 정보 복사 | API가 JOIN 없이 **단일 SELECT**로 0.5초 폴링 응답 가능 |
| `product_id_fk` 유지 | 상품 삭제 시 `SET NULL`로 참조 무결성 보장, 비정규화 필드는 스냅샷으로 유지 |
| TTL 30일 | `expires_at` 컬럼으로 오래된 광고 자동 만료 → 크론 DELETE로 정리 |

### FK 전략

| 관계 | 동작 |
|------|------|
| `detected_object_* → vod` | `ON DELETE CASCADE` — VOD 삭제 시 탐지 결과 자동 삭제 |
| `serving.shopping_ad → vod` | `ON DELETE CASCADE` — VOD 삭제 시 광고 자동 삭제 |
| `serving.shopping_ad → homeshopping_product` | `ON DELETE SET NULL` — 상품 삭제 시 광고는 유지 (비정규화 필드 존재) |

### 인덱스 전략

| 테이블 | 인덱스 | 쿼리 패턴 |
|--------|--------|----------|
| `detected_object_yolo` | `(vod_id_fk, frame_ts)` | VOD별 시간순 탐지 조회 |
| `detected_object_clip` | `(vod_id_fk, frame_ts) WHERE context_valid` | 유효한 개념만 필터 |
| `detected_object_stt` | `(vod_id_fk, start_ts, end_ts)` | 구간 범위 조회 |
| `serving.shopping_ad` | `(vod_id_fk, ts_start, ts_end)` | `ts_start <= $t AND ts_end >= $t` 실시간 조회 |
| `serving.shopping_ad` | `(expires_at)` | TTL 만료 정리 크론 |

---

## 신규 테이블 요약

| 계층 | 테이블 | 생산 | 소비 | DDL 파일 |
|------|--------|------|------|----------|
| Silver | `detected_object_yolo` | Object_Detection | Shopping_Ad | `schemas/create_detection_tables.sql` |
| Silver | `detected_object_clip` | Object_Detection | Shopping_Ad | `schemas/create_detection_tables.sql` |
| Silver | `detected_object_stt` | Object_Detection | Shopping_Ad | `schemas/create_detection_tables.sql` |
| Silver | `tv_schedule` | 외부 EPG | Shopping_Ad | `schemas/create_tv_schedule.sql` |
| Silver | `homeshopping_product` | Shopping_Ad | Shopping_Ad, API_Server | `schemas/create_homeshopping_tables.sql` |
| Gold | `serving.shopping_ad` | Shopping_Ad | API_Server | `schemas/create_shopping_ad_serving.sql` |

### vod 컬럼 추가 (마이그레이션)

| 컬럼 | 타입 | 용도 | 마이그레이션 파일 |
|------|------|------|-----------------|
| `youtube_video_id` | VARCHAR(20) | YouTube iframe 재생 | `migrations/20260318_add_trailer_columns_to_vod.sql` |
| `duration_sec` | REAL | 영상 길이 (초) | 동일 |
| `trailer_processed` | BOOLEAN | Object_Detection 처리 완료 여부 | 동일 |

---

## DB 실행 순서

스키마 확정 후 VPC에서 아래 순서로 실행한다.

```bash
# 0. 환경 변수 로드
set -a && source .env && set +a

# 1. 기존 파일 (DB 미생성분)
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schemas/create_homeshopping_tables.sql

# 2. 탐지 결과 3종 테이블
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schemas/create_detection_tables.sql

# 3. EPG 편성표
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schemas/create_tv_schedule.sql

# 4. vod 컬럼 추가 마이그레이션
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/migrations/20260318_add_trailer_columns_to_vod.sql

# 5. 쇼핑 광고 서빙 테이블 (homeshopping_product FK 참조)
PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
  -f Database_Design/schemas/create_shopping_ad_serving.sql
```

### 검증 쿼리

```sql
-- 테이블 생성 확인
\dt public.detected_object_*
\dt public.tv_schedule
\dt public.homeshopping_product
\dt serving.shopping_ad

-- 컬럼/타입 검증
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name IN ('detected_object_yolo','detected_object_clip','detected_object_stt','tv_schedule','shopping_ad')
ORDER BY table_name, ordinal_position;

-- vod 마이그레이션 컬럼 확인
SELECT column_name, data_type, column_default
FROM information_schema.columns
WHERE table_name = 'vod'
  AND column_name IN ('youtube_video_id', 'duration_sec', 'trailer_processed');

-- 인덱스 확인
\di public.idx_det_*
\di public.idx_tv_*
\di serving.idx_sa_*

-- FK 무결성 테스트 (에러 발생해야 정상)
INSERT INTO detected_object_yolo (vod_id_fk, frame_ts, label, confidence, bbox)
VALUES ('NONEXISTENT', 0.0, 'test', 0.5, '{0,0,1,1}');

-- serving.shopping_ad 쿼리 패턴 테스트
EXPLAIN ANALYZE
SELECT * FROM serving.shopping_ad
WHERE vod_id_fk = 'SOME_VOD_ID'
  AND ts_start <= 30.0 AND ts_end >= 30.0
  AND expires_at > NOW();
```
