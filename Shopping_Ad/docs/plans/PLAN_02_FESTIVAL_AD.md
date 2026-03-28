# PLAN_02 — 축제 + 제철장터 광고 매칭 파이프라인

- **브랜치**: Shopping_Ad
- **작성일**: 2026-03-20 (2026-03-23 업데이트)
- **선행 조건**: Object_Detection 19건 배치 완료

---

## 구현 현황

### Phase 1 — 축제 데이터 수집 ✅

| 파일 | 상태 |
|------|------|
| `scripts/crawl_festivals.py` | ✅ Visit Korea API, 4~5월 63건/50지역 |
| `data/region_festivals.yaml` | ✅ region→축제 매핑 |

### Phase 2 — 제철장터 크롤링 ✅

| 파일 | 상태 |
|------|------|
| `scripts/crawl_seasonal_market.py` | ✅ LG헬로비전 API, 10개 상품/21개 편성 |
| `data/seasonal_market.json` | ✅ 실제 상품 데이터 |

### Phase 3 — 매칭 엔진 ✅

| 파일 | 상태 |
|------|------|
| `src/festival_matcher.py` | ✅ region → 축제 매칭 |
| `src/seasonal_matcher.py` | ✅ 키워드 → 제철장터 실제 상품 매칭 |

### Phase 4 — VOD 요약 + 통합 매칭 ✅

| 파일 | 상태 |
|------|------|
| `scripts/build_vod_summary.py` | ✅ parquet 4종 → VOD별 집계 (도시 우선순위) |
| `scripts/run_ad_matching.py` | ✅ 축제 6건 + 제철장터 4건 = 10건 (smry 보강 + 스코어링) |

### Phase 4.5 — 팝업 포맷 + 매칭 정확도 개선 ✅

| 파일 | 상태 |
|------|------|
| `src/seasonal_matcher.py` | ✅ 방송 중/예정 2종 포맷 (popup_text_live / popup_text_scheduled) |
| `scripts/run_ad_matching.py` | ✅ DB smry 보강 키워드 + 스코어링 (지역 일치 +2, primary_region +1, smry 음식 +1) |
| `docs/plans/PLAN_03_SEASONAL_POPUP_FORMAT.md` | ✅ 팝업 포맷 설계 문서 |
| `docs/plans/PLAN_04_SMRY_MATCHING.md` | ✅ smry 매칭 설계 문서 |

### Phase 5 — DB 적재 (대기)

| 항목 | 담당 | 상태 |
|------|------|------|
| serving 스키마 + shopping_ad DDL | 조장 | 🔲 |
| 적재 스크립트 | Shopping_Ad | 🔲 |

---

## 매칭 결과 (2026-03-23)

### 축제 매칭 (8건)

| VOD | primary_region | 축제 |
|-----|---------------|------|
| 동원아 영월 | 영월 | 단종문화제 (04.24~04.26) |
| 동원아 제주 | 제주 | 제주마 입목 문화축제 (04.18~04.19) |
| 동원아 소고기 | 제주 | 제주마 입목 문화축제 |
| 서울촌놈 부산 | 부산 | 해운대 모래축제 (05.15~05.18) |
| 서울촌놈 대전 | 대전 | 대덕물빛축제 (04.04~04.18) |
| 춘천 닭갈비 | 춘천 | 춘천마임축제 (05.24~05.31) |
| 알토란 순두부 | 창원 | 진해군항제 (03.27~04.05) |
| 수육국수 | 제주 | 제주마 입목 문화축제 |

### 제철장터 매칭 (4건, VOD당 1건 + 스코어링 적용)

| VOD | 상품 | 키워드 | score | 비고 |
|-----|------|--------|-------|------|
| food_altoran_418 | 아산 포기김치 | 김치 | 1 | |
| food_altoran_490 | 아산 포기김치 | 김치 | 2 | smry 음식 가산 |
| travel_chonnom_03 | 아산 포기김치 | 김치 | 1 | |
| travel_dongwon_12 | 아산 포기김치 | 김치 | 2 | smry 음식 가산 |

> 제철장터 10개 상품 중 매칭되는 건 김치 관련 1종. 재크롤링(4/7~8) 후 상품 변경 시 결과 달라질 수 있음.

### 매칭 안 된 VOD (9건)

| VOD | 이유 |
|-----|------|
| food_altoran_440 | 한우 제철장터 상품 없음 |
| food_local_keyjo | 키조개 제철장터 상품 없음 + 보령 축제 없음 |
| food_local_memill | 메밀 제철장터 상품 없음 + 강원 축제 매칭 실패 |
| food_local_samchi | 삼치 제철장터 상품 없음 |
| food_local_sugyuk | 수육 제철장터 상품 없음 |
| travel_chonnom_05 | 청주 축제 없음 |
| travel_chonnom_09 | 전주 축제 없음 + 비빔밥 제철장터 없음 |
| travel_dongwon_11 | 정선 축제 없음 + STT 0건 |
| travel_dongwon_15 | 축제 있으나 제철장터 매칭 없음 |

---

---

## 매칭/송출 규칙 (2026-03-23 확정)

### 제철장터 매칭 정확도
- 곁들이 키워드는 **차라리 안 넣는 게 나음**
- **Top 3 키워드**에 포함될 때만 제철장터 매칭
- 상품명 지역 파싱 (예: "아산 포기김치" → "아산") → VOD 지역과 매칭 정확도 제고

### 광고 노출 타이밍 (Trigger Point)
- **영상 50% 이상 지점**에서만 광고
- **OCR(자막) 없는 클린한 화면**에서 출력
- 노출 우선순위: **축제 > 제철장터**

---

## 발표 전 TODO

- [x] Top 3 키워드 필터 + 지역 파싱 구현
- [x] 50% + 클린화면 타이밍 구현
- [x] 축제 팝업 GIF 63건 생성
- [x] VOD 영상 삽입 샘플 (FFmpeg)
- [x] 제철장터 팝업 포맷 확정 (방송 중/예정 2종)
- [x] smry 기반 매칭 정확도 개선 (스코어링)
- [ ] 제철장터 재크롤링 (4/7~8 시점, 상품 변경 가능)
- [ ] DB 적재 (조장 DDL 후)
- [ ] 19개 테스트 에이전트 생성
