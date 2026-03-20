# PLAN_02 — 지자체 축제 광고 매칭 파이프라인

- **브랜치**: Shopping_Ad
- **작성일**: 2026-03-20
- **선행 조건**: Object_Detection 배치 처리 완료, Visit Korea 축제 크롤링 완료

---

## 목표

Object_Detection이 추출한 VOD별 region(지역명)을 Visit Korea 축제 데이터와 매칭하여
지자체 광고 팝업을 생성하고 `serving.shopping_ad`에 적재한다.

---

## 구현 현황

### Phase 1 — 축제 데이터 수집 ✅

| 항목 | 파일 | 상태 |
|------|------|------|
| Visit Korea API 크롤러 | `scripts/crawl_festivals.py` | ✅ 완료 |
| 축제 JSON 저장 | `data/festivals.json` | ✅ 63건 |
| region→축제 yaml | `data/region_festivals.yaml` | ✅ 50지역 |

### Phase 2 — 매칭 엔진 ✅

| 항목 | 파일 | 상태 |
|------|------|------|
| region 매칭 | `src/festival_matcher.py` | ✅ 완료 |
| E2E 검증 | `scripts/test_festival_match.py` | ✅ 7/17 매칭 |

### Phase 3 — DB 적재 (예정)

| 항목 | 담당 | 상태 |
|------|------|------|
| `serving.shopping_ad` DDL 실행 | 조장 (황대원) | 🔲 대기 |
| `detected_object_ocr` DDL 실행 | 조장 | 🔲 대기 |
| `vod_ad_summary` DDL 실행 | 조장 | 🔲 대기 |
| 적재 스크립트 | Shopping_Ad | 🔲 예정 |

### Phase 4 — 제철장터 연계 (예정)

| 항목 | 상태 |
|------|------|
| `seasonal_market` 편성표 데이터 확보 | 🔲 예정 |
| 음식 ad_category → 제철장터 상품 매칭 | 🔲 예정 |

### Phase 5 — 생성형 AI 팝업 (예정)

| 항목 | 상태 |
|------|------|
| 축제 없는 지역 → AI 생성 관광 팝업 | 🔲 조장 계획 |

---

## 매칭 로직

### 관광지 매칭 (구현 완료)

```
Object_Detection 산출물
  vod_ad_summary: {vod_id, ad_category="관광지", region="경주"}
    │
    └──→ festival_matcher.match("경주")
           │
           └──→ region_festivals.yaml 조회
                  경주:
                    - name: 경주 대릉원돌담길 축제
                      period: 2026.04.03~2026.04.05
                  │
                  └──→ 팝업 데이터 생성
                         popup_title: "📍 경주 축제 안내"
                         popup_body: "경주 대릉원돌담길 축제\n📅 2026.04.03~2026.04.05"
                         ad_action_type: "local_gov_popup"
```

### 음식 매칭 (예정)

```
Object_Detection 산출물
  vod_stt_concept: {keyword="한우", ad_hints="횡성 한우 — 제철장터"}
    │
    └──→ seasonal_market 테이블 조회 (or ad_hints 직접 사용)
           │
           └──→ 팝업 데이터 생성
                  popup_title: "🛒 제철장터 상품 안내"
                  popup_body: "횡성 한우 — 제철장터"
                  ad_action_type: "seasonal_market"
```

---

## 검증 결과

### E2E 매칭 (2026-03-20)

| region | 축제 | 결과 |
|--------|------|------|
| 부산 | 해운대 모래축제 | ✅ |
| 경주 | 대릉원돌담길 축제 | ✅ |
| 대전 | 대덕물빛축제 | ✅ |
| 영월 | 단종문화제 | ✅ |
| 제주 | 제주마 입목 문화축제 | ✅ |
| 춘천 | 춘천마임축제 | ✅ |
| 순천 | - | ❌ 4~5월 축제 미등록 |
| 전주 | - | ❌ 4~5월 축제 미등록 |
| 광주 | - | ❌ 4~5월 축제 미등록 |

미매칭 지역 → Phase 5 생성형 AI로 해결 예정
