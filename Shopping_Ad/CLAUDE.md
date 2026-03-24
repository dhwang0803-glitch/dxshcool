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
  음식: Top 3 키워드만 → seasonal_market.json 실제 상품 매칭
        상품명 지역 파싱 → VOD 지역과 우선 매칭
  → shopping_ad_candidates.parquet 저장 (ts_start/ts_end 포함)

[매칭 규칙 — 2026-03-23 확정]
  1. 곁들이 키워드 제거: Top 3 키워드만 제철장터 매칭
  2. 상품명 지역 파싱: "아산 포기김치" → "아산" → VOD 지역과 우선 매칭
  3. 노출 우선순위: 축제(local_gov_popup) > 제철장터(seasonal_market)

[광고 타이밍 — 2026-03-23 확정]
  1. 영상 50% 이상 지점에서만 광고
  2. OCR(자막) 없는 클린한 화면에서 출력
  3. ts_start/ts_end = 해당 구간의 frame_ts

━━━ 실시간 서빙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

시청자 VOD 재생
  → API_Server: serving.shopping_ad 조회 (ts_start <= 현재시간 <= ts_end)
  → 축제 우선 → "OO 지역 축제 안내" (지자체 팝업)
  → 제철장터 → "제철장터에서 OO 방송 중" (채널 이동/시청예약)
  → 10초 미응답 → 자동 최소화
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
│   ├── generate_festival_gif.py ← 팝업 HTML → Playwright → GIF 일괄 생성
│   ├── insert_ad_to_vod.py      ← GIF → VOD 영상 삽입 샘플 (FFmpeg)
│   └── test_festival_match.py   ← E2E 매칭 검증
├── templates/
│   ├── popup_*.html             ← 축제 팝업 광고 HTML (가로형 520x300)
│   └── images/                  ← 축제 배경 사진 6장
├── config/
├── data/                        ← (gitignore)
│   ├── festivals.json
│   ├── region_festivals.yaml
│   ├── seasonal_market.json
│   ├── vod_ad_summary.parquet
│   ├── shopping_ad_candidates.parquet
│   └── ad_gifs/                 ← 생성된 팝업 GIF (popup_*.gif)
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
| `public.vod.smry` | smry 기반 매칭 보강 (지역/음식 키워드 추출) |

### 다운스트림 (쓰기)

`shopping_ad_candidates.parquet` 출력 필드:

| 필드 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `ad_category` | str | `관광지` / `음식` |
| `ad_action_type` | str | `local_gov_popup` / `seasonal_market` |
| `product_name` | str | 축제명 또는 상품명 |
| `channel` | str | 제철장터 채널명 (채널번호 25) |
| `popup_text_live` | str | 방송 중 팝업 문구 (제철장터만) |
| `popup_text_scheduled` | str | 방송 예정 팝업 문구 (제철장터만) |
| `popup_title` / `popup_body` | str | 축제 팝업 문구 (축제만) |
| `ts_start` / `ts_end` | float | 광고 노출 타임스탬프 |
| `match_score` | int | 스코어링 점수 (제철장터만) |
| `priority` | int | 1=축제(우선), 2=제철장터 |

적재 대상: `serving.shopping_ad` (DDL 대기)

---

## 현재 상태 (2026-03-24)

| 항목 | 상태 |
|------|------|
| Visit Korea 축제 크롤러 | ✅ 63건/50지역 |
| 제철장터 크롤러 | ✅ 10개 상품/21개 편성 |
| festival_matcher | ✅ 완료 |
| seasonal_matcher | ✅ 실제 상품 매칭 + 방송 중/예정 2종 포맷 |
| VOD 요약 집계 (도시 우선순위) | ✅ 완료 |
| 통합 매칭 파이프라인 | ✅ 축제 6건 + 제철장터 4건 = 10건 (smry 보강 + 스코어링) |
| 축제 팝업 GIF 생성 | ✅ 63건 완료 (팝업 가로형, 사진 배경) |
| VOD 영상 삽입 샘플 | ✅ FFmpeg 페이드인/아웃 (진해군항제) |
| DB 적재 | 🔲 serving DDL 대기 |

---

## 협업 규칙

- `main` 직접 Push 금지 — PR 필수
- Object_Detection parquet 스키마 변경 시 인터페이스 업데이트
- 발표 전 제철장터 재크롤링 필요
