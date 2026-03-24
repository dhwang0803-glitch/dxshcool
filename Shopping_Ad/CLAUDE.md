# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

---

## 모듈 역할

**Object_Detection 산출물 소비 → 제철장터 상품 매칭 + 지자체 광고 연계 → `serving.shopping_ad` 적재**

Object_Detection이 추출한 VOD별 ad_category(음식/관광지) + region(지역명)을 기반으로,
음식 카테고리는 제철장터 채널 실제 상품과 연계하고,
관광지 카테고리는 지자체 축제/관광 팝업 광고를 생성하여
`serving.shopping_ad`에 적재한다.

### 광고 2종 (2026-03-19 전략 확정)

| 카테고리 | 트리거 | 광고 액션 | 예시 |
|---------|--------|-----------|------|
| **음식** | STT "추어탕" 탐지 | 제철장터 실제 상품 매칭 (채널 이동/시청예약) | "🛒 남원추어탕 — 제철장터 방송 중" |
| **관광지/지역** | STT+OCR "영월" 탐지 | Visit Korea 축제 팝업 | "📍 영월 단종문화제 04.24~04.26" |

> **대상 VOD**: `genre_detail IN ('여행', '음식_먹방')`
> **홈쇼핑 매칭 폐기** (2026-03-19)

### 데이터 플로우

```
━━━ 1회 사전 준비 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Visit Korea 축제 크롤링]
  scripts/crawl_festivals.py → data/region_festivals.yaml
  4~5월 축제 63건 / 50개 지역

[제철장터 편성표 크롤링]
  scripts/crawl_seasonal_market.py → data/seasonal_market.json
  LG헬로비전 API → 이번 주 제철장터 상품 (발표 전 재크롤링)

━━━ Object_Detection parquet 소비 ━━━━━━━━━━━━━━━━━━━━━━━━

[VOD 요약 집계]
  scripts/build_vod_summary.py
  parquet 4종 → VOD별 ad_category + primary_region + trigger_count
  도시 우선순위: 명소(경기전, 태종대)보다 도시(전주, 부산) 우선

━━━ 통합 매칭 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[scripts/run_ad_matching.py]
  관광지: primary_region → region_festivals.yaml 축제 매칭
  음식: STT 키워드 → seasonal_market.json 실제 상품 매칭
  → shopping_ad_candidates.parquet 저장

━━━ 실시간 서빙 (예정) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

시청자 VOD 재생
  → API_Server: serving.shopping_ad 조회
  → 음식 → "제철장터에서 OO 방송 중" (채널 이동/시청예약)
  → 관광지 → "OO 지역 축제 안내" (지자체 팝업)
```

---

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/
│   ├── festival_matcher.py      ← region → 축제 매칭
│   ├── seasonal_matcher.py      ← 키워드 → 제철장터 실제 상품 매칭
│   ├── db_writer.py             ← DB 적재 유틸
│   └── crawlers/                ← (레거시) 홈쇼핑 크롤러 — 미사용
├── scripts/
│   ├── crawl_festivals.py       ← Visit Korea 축제 크롤링
│   ├── crawl_seasonal_market.py ← LG헬로비전 제철장터 크롤링
│   ├── build_vod_summary.py     ← parquet 4종 → VOD 요약 집계
│   ├── run_ad_matching.py       ← 축제+제철장터 통합 매칭
│   └── test_festival_match.py   ← E2E 매칭 검증
├── config/
├── data/                        ← (gitignore)
│   ├── festivals.json
│   ├── region_festivals.yaml
│   ├── seasonal_market.json
│   ├── vod_ad_summary.parquet
│   └── shopping_ad_candidates.parquet
└── docs/
```

**`Shopping_Ad/` 루트에 `.py` 직접 생성 금지.**

---

## 인터페이스

### 업스트림 (읽기)

| 소스 | 용도 |
|------|------|
| Object_Detection parquet 4종 | VOD 요약 집계 입력 |
| `data/region_festivals.yaml` | 축제 매칭 |
| `data/seasonal_market.json` | 제철장터 실제 상품 매칭 |

### 다운스트림 (쓰기)

| 대상 | 컬럼 | 비고 |
|------|------|------|
| `serving.shopping_ad` | vod_id_fk, ad_category, ad_action_type, product_name, channel 등 | DDL 대기 |

---

## 현재 상태 (2026-03-23)

| 항목 | 상태 |
|------|------|
| Visit Korea 축제 크롤러 | ✅ 63건/50지역 |
| 제철장터 크롤러 | ✅ 10개 상품/21개 편성 |
| festival_matcher | ✅ 완료 |
| seasonal_matcher | ✅ 실제 상품 매칭 |
| VOD 요약 집계 (도시 우선순위) | ✅ 완료 |
| 통합 매칭 파이프라인 | ✅ 축제 8건 + 제철장터 13건 |
| DB 적재 | 🔲 serving DDL 대기 |

---

## 협업 규칙

- `main` 직접 Push 금지 — PR 필수
- Object_Detection parquet 스키마 변경 시 인터페이스 업데이트
- 발표 전 제철장터 재크롤링 필요
