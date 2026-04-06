# 세션 리포트 — 2026-04-05

## 작업 요약

### 1. 제철장터 재크롤링 (이번 주 기준)
- **기간**: 2026-04-05 ~ 2026-04-11 (7일, 21건)
- **상품 10종**: 남원추어탕, 도라지배즙, 군산 박대, 아산 포기김치, 귀리 두유, 경기 노가리(신규), 박수홍 흑염소, 홍성마늘등심, 양평 꿀갈비, 양구 시래기
- **산출물**: `data/seasonal_market.json`, `data/seasonal_market_products.yaml`

### 2. 골목식당 156회 추가 (추어탕 에피소드)
- **VOD**: 백종원의 골목식당 156회
- **DB full_asset_id**: `cjc|M4862144LSGL00455001` (DB 등록 확인)
- **YouTube**: `sg0bGGSok_s`
- **다운로드**: `Object_Detection/data/batch_target/food_golmok_156.mp4` (26.6MB)

### 3. Object_Detection 파이프라인 실행
골목식당 156회 4종 멀티모달 분석 결과:

| 모델 | 건수 | 주요 결과 |
|------|------|----------|
| YOLO | 19건 | food_detected (conf 0.50~0.96) |
| CLIP | 25건 | 한국 전통 반찬 밥상, 해산물 한국 요리 등 |
| STT | 9건 | 추어탕(4), 만두(2), 김치(1), 들깨(2) |
| OCR | 63건 | 추어탕, 골목식당 등 자막 |

### 4. 통합 매칭 결과
- **기존 7건 → 8건** (골목식당 1건 추가)
- **신규 매칭**: `food_golmok_156` → 남원추어탕 (4/5 05:55~06:55)
- **ts_start**: 150초 (2분 30초) — 추어탕 클로즈업 타이밍 수동 보정
- **signal_source**: yolo, **matched_keyword**: 추어탕

### 5. PPT 슬라이드 수정
- PAGE 4 좌측 관광지 사례: 해운대 모래축제 → **단종문화제** 변경
- 실제 parquet 데이터 기반 (CLIP 봄풍경 0.30 + OCR "영월")
- 파일: `피드백 수정 VERSION3.pptx`

---

## 변경 파일 목록

### 데이터 (gitignore, 커밋 대상 아님)
| 파일 | 변경 내용 |
|------|----------|
| `Shopping_Ad/data/seasonal_market.json` | 4/5~4/11 재크롤링 |
| `Shopping_Ad/data/seasonal_market_products.yaml` | 상품 10종 갱신 |
| `Shopping_Ad/data/vod_id_mapping.json` | food_golmok_156 추가 |
| `Shopping_Ad/data/shopping_ad_candidates.parquet` | 8건 (골목식당 추가) |
| `Shopping_Ad/data/vod_ad_summary.parquet` | 20건 (골목식당 추가) |
| `Object_Detection/data/batch_target/vod_metadata.json` | food_golmok_156 추가 |
| `Object_Detection/data/batch_target/food_golmok_156.mp4` | 영상 다운로드 |
| `Object_Detection/data/parquet_output/vod_detected_object.parquet` | YOLO 19건 추가 |
| `Object_Detection/data/parquet_output/vod_clip_concept.parquet` | CLIP 25건 추가 |
| `Object_Detection/data/parquet_output/vod_stt_concept.parquet` | STT 9건 추가 |
| `Object_Detection/data/parquet_output/vod_ocr_concept.parquet` | OCR 63건 추가 |

### PPT (별도 폴더, 커밋 대상 아님)
| 파일 | 변경 내용 |
|------|----------|
| `dxschool ppt/build_feedback_v2.py` | PAGE 4 단종문화제 변경 + VERSION3 출력 |
| `dxschool ppt/피드백 수정 VERSION3.pptx` | 빌드 결과 |

---

## 조장 전달 사항

### DB 적재 필요 파일

```
1. Shopping_Ad/data/seasonal_market.json
   → public.seasonal_market 적재 (현재 DB 0건)

2. Shopping_Ad/data/shopping_ad_candidates.parquet
   → serving.shopping_ad에 골목식당 1건 INSERT

3. Object_Detection/data/parquet_output/vod_detected_object.parquet
   Object_Detection/data/parquet_output/vod_clip_concept.parquet
   Object_Detection/data/parquet_output/vod_stt_concept.parquet
   Object_Detection/data/parquet_output/vod_ocr_concept.parquet
   → detected_object_yolo/clip/stt + ocr에 골목식당 추가분 적재
```

---

## 최종 매칭 현황 (8건)

| VOD | 카테고리 | 상품/축제 | 타이밍 |
|-----|---------|----------|--------|
| food_altoran_490 | 음식 | 아산 포기김치 | @366초 |
| **food_golmok_156** | **음식** | **남원추어탕** | **@150초** |
| food_altoran_496 | 관광지 | 진해군항제 | @356초 |
| food_local_dakgalbi | 관광지 | 춘천마임축제 | @146초 |
| travel_chonnom_01 | 관광지 | 해운대 모래축제 | @105초 |
| travel_chonnom_07 | 관광지 | 대덕물빛축제 | @120초 |
| travel_dongwon_06 | 관광지 | 단종문화제 | @477초 |
| travel_dongwon_16 | 관광지 | 제주마 입목 문화축제 | @321초 |
