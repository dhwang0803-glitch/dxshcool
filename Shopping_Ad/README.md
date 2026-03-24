# Shopping_Ad

Object_Detection 산출물 소비 → 제철장터 상품 매칭 + 지자체 축제 광고 → `serving.shopping_ad` 적재

## 역할

- Object_Detection parquet 4종 (YOLO/CLIP/STT/OCR) → VOD별 요약 집계
- 관광지 인식 → Visit Korea 축제 매칭 → 지자체 광고 팝업
- 음식 인식 → LG헬로비전 제철장터 실제 상품 매칭 → 채널 이동/시청예약

## 실행

```bash
conda activate myenv
cd Shopping_Ad

# 1. 축제 크롤링 (4~5월)
python scripts/crawl_festivals.py

# 2. 제철장터 편성표 크롤링
python scripts/crawl_seasonal_market.py

# 3. VOD 요약 집계
python scripts/build_vod_summary.py

# 4. 통합 매칭 (축제 + 제철장터)
python scripts/run_ad_matching.py
```

## 현재 상태 (2026-03-23)

- 축제: 63건/50지역 (4~5월)
- 제철장터: 10개 상품/21개 편성 (이번 주)
- 통합 매칭: 축제 8건 + 제철장터 13건 = 21건 (19개 VOD 대상)
