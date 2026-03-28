> ⚠️ **OUTDATED (2026-03-19)**: 임베딩 기반 매칭 → region 기반 축제 매칭으로 전환.
> 현재: festival_matcher.py + region_festivals.yaml 방식.

# PLAN_01 — Shopping_Ad Matcher 설계

## 목표

Object_Detection 산출물(YOLO/CLIP/STT)을 `product_catalog`과 의미 기반으로 매칭하여
`serving.shopping_ad`에 광고 후보를 생성한다.

---

## 핵심 아키텍처 — 임베딩 기반 의미 매칭

rule-based 카테고리 맵 대신 **텍스트 임베딩 + pgvector 코사인 유사도**로 매칭한다.

```
[Object Detection 산출물]
  YOLO label:    "비빔밥"
  CLIP concept:  "해변 바다 리조트 수영장"
  STT keyword:   "여행"
        ↓ sentence-transformers 텍스트 임베딩 (384d)
        ↓
[pgvector: public.detected_objects.embedding]
        ↓ cosine similarity (pgvector <=> 연산자)
[pgvector: product_catalog.embedding]
  product_name: "제주 여행 패키지", "한식 밀키트" 등
        ↓
[serving.shopping_ad]
  vod_id | ts_start | ts_end | product_id | confidence
```

### 장점

| | rule-based | embedding-based |
|--|-----------|----------------|
| 신규 상품 추가 | 룰 수동 수정 | 임베딩만 추가 |
| 의미 확장 | "비빔밥"→한식만 | "비빔밥"→밀키트/배달앱/식기 연결 |
| 유지보수 | 카테고리 맵 관리 | 불필요 |

---

## 카테고리별 신호 우선순위 (Fusion Rule)

| 카테고리 | 주력 | 보조 | 통과 조건 | 억제 조건 |
|---------|------|------|----------|----------|
| 한식 메뉴 | YOLO 파인튜닝 | STT, CLIP | YOLO 탐지 1건 이상 | - |
| 가전/가구 | base YOLO (COCO) | CLIP | COCO 객체 탐지 | - |
| 여행지/배경 | CLIP | STT | CLIP ≥ 0.26 + STT 여행 키워드 1건 이상 | 스튜디오 장면 비율 높음 |
| 패션/뷰티 | CLIP | base YOLO 보조 객체 | CLIP ≥ 0.26 | 단독 CLIP만이면 엄격 |

### COCO base YOLO 광고 연결 객체

| COCO 라벨 | 광고 카테고리 |
|----------|-------------|
| `tv`, `laptop`, `cell phone` | 가전/IT |
| `refrigerator`, `microwave`, `oven`, `sink` | 주방가전 |
| `couch`, `chair`, `bed`, `dining table` | 가구/인테리어 |
| `handbag`, `backpack`, `suitcase` | 패션/여행용품 |
| `bottle`, `cup`, `bowl`, `fork`, `knife` | 주방용품 |

---

## DB 스키마 요구사항 (황대원 협의 필요)

### 신규 컬럼

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.detected_objects` | `embedding` | `vector(384)` | label/concept 텍스트 임베딩 |
| `product_catalog` | `embedding` | `vector(384)` | 상품명 임베딩 |

### 신규 테이블

**`product_catalog`**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `product_id` | SERIAL PK | 상품 ID |
| `product_name` | VARCHAR | 상품명 |
| `category` | VARCHAR | 카테고리 |
| `price` | INTEGER | 가격 |
| `image_url` | VARCHAR | 상품 이미지 |
| `purchase_url` | VARCHAR | 구매 링크 |
| `embedding` | vector(384) | 상품명 임베딩 |

**`serving.shopping_ad`**

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | VARCHAR(64) | 영상 식별자 |
| `ts_start` | FLOAT | 팝업 시작 타임스탬프 |
| `ts_end` | FLOAT | 팝업 종료 타임스탬프 |
| `product_id` | INTEGER | 매칭된 상품 ID |
| `ad_category` | VARCHAR | 광고 카테고리 |
| `source` | VARCHAR | 탐지 출처 (YOLO/CLIP/STT) |
| `confidence` | FLOAT | 유사도 점수 |

---

## 임베딩 모델

```python
# 한국어 지원, 384차원, sentence-transformers 호환
model = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
```

---

## 구현 단계

### Phase 1 — matcher.py (핵심 매칭 엔진)

```
입력:
  - vod_id
  - detected labels (YOLO parquet)
  - clip concepts (CLIP parquet)
  - stt keywords (STT parquet)

처리:
  1. label/concept/keyword 텍스트 임베딩
  2. pgvector cosine similarity → product_catalog 상위 K개
  3. fusion rule 적용 (카테고리별 통과 조건)
  4. ts_start/ts_end 윈도우 생성

출력:
  - serving.shopping_ad 레코드
```

### Phase 2 — run_shopping_ad.py (배치 스크립트)

```bash
python scripts/run_shopping_ad.py --vod-id {vod_id}
python scripts/run_shopping_ad.py --all   # 전체 배치
```

---

## 선행 조건 (블로커)

| 항목 | 담당 | 상태 |
|------|------|------|
| `product_catalog` 데이터 확보 | 팀 공통 | 🔲 미확보 |
| `serving.shopping_ad` 스키마 확정 | 황대원 | 🔲 미확정 |
| `public.detected_objects.embedding` 컬럼 추가 | 황대원 | 🔲 미확정 |
| Object_Detection 파이프라인 실행 완료 | Object_Detection | 🔲 YOLO 파인튜닝 진행 중 |
