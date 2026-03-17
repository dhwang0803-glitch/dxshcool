# PLAN_01 — Shopping_Ad 파이프라인 구현

- **브랜치**: Shopping_Ad
- **작성일**: 2026-03-16
- **선행 조건**: Object_Detection Phase 1~4 완료 (PR #31), PR #38 머지 예정

---

## 목표

Object_Detection이 생성한 3종 parquet을 소비하여,
현재 방영 중인 VOD 장면에서 쇼핑 광고 팝업 후보를 생성하고
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

#### Step 1 — 상품 카탈로그 로드

```python
# config/ad_config.yaml
catalog:
  path: data/product_catalog.csv  # 상품명, category, ad_url, thumbnail_url
```

#### Step 2 — 멀티모달 신호 통합

```
[우선순위]
1. STT 키워드 매칭 (가장 명확한 신호 — 발화 직접 확인)
   keyword → ad_category → 카탈로그 필터
2. CLIP 개념 매칭 (context_valid=True만 사용)
   concept + ad_category → 카탈로그 필터
3. YOLO bbox 보완 (CLIP 미탐지 구간 보조)
   label → category 매핑 → 카탈로그 필터
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
| `serving.shopping_ad` 스키마 | Database_Design(황대원) | 🔲 협의 필요 |
| `vod_stt_concept.parquet` 키워드 확충 | Object_Detection(박아름) ↔ Shopping_Ad | 🔲 카테고리별 50개+ 목표 |
| 상품 카탈로그 (`product_catalog.csv`) | 팀 공통 | 🔲 데이터 확보 필요 |
| API_Server WebSocket `/ad/popup` 연동 | API_Server(PLAN_06) | 🔲 serving.shopping_ad 완료 후 |

---

## 기대 효과

| 항목 | 현재 | 구현 후 |
|------|------|---------|
| 광고 트리거 | 없음 | VOD 장면 실시간 매칭 |
| 한식/지방특산물 광고 | STT 2건(파일럿) | STT + CLIP + YOLO 3중 신호 |
| API_Server 연동 | popular_fallback | `/ad/popup` WebSocket 실시간 팝업 |
