# PLAN_01 — Shopping_Ad 파이프라인 구현

- **브랜치**: Shopping_Ad
- **작성일**: 2026-03-16
- **선행 조건**: Object_Detection Phase 1~4 완료 (PR #31), PR #38 머지 예정

---

## 목표

> **2026-03-19 방향 전환**: 홈쇼핑 연동 폐기 → 지자체 광고 팝업 + 제철장터 채널 연계로 전환.

Object_Detection이 생성한 3종 parquet을 소비하여,
VOD 장면에서 **관광지/지역 인식 → 지자체 광고 팝업**, **음식 인식 → 제철장터 채널 연계** 후보를 생성하고
VPC `serving.shopping_ad` 테이블에 적재한다.

---

## 입력 / 출력

### 입력 (Object_Detection 산출물)

| 파일 | 핵심 컬럼 | 내용 |
|------|----------|------|
| `vod_detected_object.parquet` | `vod_id`, `frame_ts`, `label`, `confidence`, `bbox` | YOLO bbox 탐지 |
| `vod_clip_concept.parquet` | `vod_id`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | CLIP 개념 태깅 |
| `vod_stt_concept.parquet` | `vod_id`, `start_ts`, `end_ts`, `keyword`, `ad_category`, `ad_hints` | STT 키워드 |

### 출력

| 대상 | 내용 |
|------|------|
| `serving.shopping_ad` (VPC) | 광고 팝업 후보 레코드 (스키마 Database_Design과 협의 후 확정) |
| `data/shopping_ad_candidates.parquet` (로컬) | VPC 적재 전 중간 검증용 |

---

## 구현 단계

### Phase 1 — 매칭 엔진 (핵심)

**목표**: 3종 parquet + 상품 카탈로그 → 광고 후보 생성

#### Step 1 — 광고 소재 및 매핑 로드

```python
# config/ad_config.yaml
local_gov_ads:
  path: data/festival_ads.csv  # 축제명, 지역, 기간, ad_image_url (OCI)
seasonal_market:
  channel_map: data/seasonal_market_map.csv  # 음식명, 제철장터 채널, 상품명
```

#### Step 2 — 멀티모달 신호 통합

```
[인식 대상별 우선순위]
관광지/지역:
  1. STT 지역명 매칭 (발화 직접 확인)
  2. CLIP 지역 개념 매칭 (context_valid=True)
  → 매칭된 지역의 축제 광고 이미지 URL 연결

음식:
  1. CLIP 음식 개념 매칭 (context_valid=True)
  2. YOLO 음식 bbox 보완 (food, bowl 등)
  3. STT 음식명 키워드 매칭
  → 제철장터 채널 상품 연계
```

#### Step 3 — 중복 제거 + 신뢰도 정렬

```python
# 동일 vod_id + 동일 ad_category 내 신뢰도 상위 1건만
# 팝업 쿨다운: 동일 카테고리 60초 이내 재노출 차단
```

#### 산출물 스키마 (잠정)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `trigger_ts` | float | 광고 트리거 타임스탬프 |
| `ad_category` | str | 광고 카테고리 |
| `product_id` | str | 카탈로그 상품 ID |
| `product_nm` | str | 상품명 |
| `signal_source` | str | `stt` / `clip` / `yolo` |
| `score` | float | 매칭 신뢰도 |
| `ad_hints` | list[str] | STT 지역 힌트 (지방특산물 등) |

> **스키마 확정 전**: `data/shopping_ad_candidates.parquet` 로컬 출력만 구현.
> `serving.shopping_ad` 적재는 Database_Design 담당자와 컬럼/타입 협의 후 진행.

---

### Phase 2 — 배치 스크립트

**파일**: `scripts/run_shopping_ad.py`

```bash
python scripts/run_shopping_ad.py \
  --detected  data/vod_detected_object.parquet \
  --clip      data/vod_clip_concept.parquet \
  --stt       data/vod_stt_concept.parquet \
  --catalog   data/product_catalog.csv \
  --output    data/shopping_ad_candidates.parquet
```

---

### Phase 3 — VPC 적재

**파일**: `scripts/ingest_to_db.py`

```bash
# serving.shopping_ad 스키마 확정 후 구현
python scripts/ingest_to_db.py \
  --input data/shopping_ad_candidates.parquet
```

---

## 완료 기준

- [ ] `src/matcher.py` — 멀티모달 신호 통합 매칭 엔진
- [ ] `scripts/run_shopping_ad.py` — 배치 실행 스크립트
- [ ] `data/shopping_ad_candidates.parquet` — 로컬 출력 확인
- [ ] `serving.shopping_ad` 스키마 Database_Design과 협의 완료
- [ ] `scripts/ingest_to_db.py` — VPC 적재 (스키마 확정 후)
- [ ] pytest 통과

---

## 의존성 및 협의 필요 항목

| 항목 | 담당 | 현황 |
|------|------|------|
| `serving.shopping_ad` 스키마 재설계 | Database_Design(황대원) | 🔲 지자체 광고 + 제철장터 반영 필요 |
| `vod_stt_concept.parquet` 키워드 확충 | Object_Detection(박아름) ↔ Shopping_Ad | 🔲 카테고리별 50개+ 목표 |
| 축제 리스트 수집 + 광고 소재 생성 파이프라인 | Shopping_Ad | 🔲 MVP 설계 필요 |
| 제철장터 채널 연계 방식 확정 | Shopping_Ad | 🔲 채널 이동/시청예약 UX 설계 |
| API_Server WebSocket `/ad/popup` 연동 | API_Server(PLAN_06) | 🔲 serving.shopping_ad 완료 후 |

---

## 기대 효과

| 항목 | 현재 | 구현 후 |
|------|------|---------|
| 광고 트리거 | 없음 | VOD 장면 실시간 매칭 |
| 한식/지방특산물 광고 | STT 2건(파일럿) | STT + CLIP + YOLO 3중 신호 |
| API_Server 연동 | popular_fallback | `/ad/popup` WebSocket 실시간 팝업 |
