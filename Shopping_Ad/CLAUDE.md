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
| **음식** | STT "추어탕" 탐지 | 제철장터 실제 상품 매칭 (채널 이동/시청예약) | "남원추어탕 — 제철장터 방송 중" |
| **관광지/지역** | STT+OCR "영월" 탐지 | Visit Korea 축제 팝업 | "영월 단종문화제 04.24~04.26" |

> **대상 VOD**: `genre_detail IN ('여행', '음식_먹방')`
> **홈쇼핑 매칭 폐기** (2026-03-19)

### 데이터 플로우

```
━━━ 1회 사전 준비 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[Visit Korea 축제 크롤링]  scripts/crawl_festivals.py → data/region_festivals.yaml
[제철장터 편성표 크롤링]    scripts/crawl_seasonal_market.py → data/seasonal_market.json

━━━ Object_Detection parquet 소비 ━━━━━━━━━━━━━━━━━━━━━━━━
[VOD 요약 집계]  scripts/build_vod_summary.py → parquet 4종 → VOD별 요약

━━━ 통합 매칭 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[scripts/run_ad_matching.py] → shopping_ad_candidates.parquet

━━━ 서빙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
API_Server → serving.shopping_ad 조회 → 축제 팝업 / 제철장터 연계
```

---

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/                ← import 전용 라이브러리 (직접 실행 X)
│   ├── festival_matcher.py     # region → 축제 매칭
│   ├── seasonal_matcher.py     # 키워드 → 제철장터 상품 매칭 + 팝업 포맷 생성
│   ├── db_writer.py            # DB 적재 유틸
│   ├── normalizer.py           # 텍스트 정규화 유틸
│   └── crawlers/               # (레거시) 홈쇼핑 크롤러 — 미사용
├── scripts/            ← 직접 실행 스크립트
│   ├── crawl_festivals.py          # Visit Korea 축제 크롤링
│   ├── crawl_seasonal_market.py    # LG헬로비전 제철장터 크롤링
│   ├── crawl_products.py           # (레거시) 상품 크롤링
│   ├── build_vod_summary.py        # parquet 4종 → VOD 요약 집계
│   ├── run_ad_matching.py          # 축제+제철장터 통합 매칭 (핵심)
│   ├── generate_festival_gif.py    # 단건 축제 팝업 GIF 생성
│   ├── generate_all_festival_gifs.py # 63건 GIF 일괄 생성
│   ├── insert_ad_to_vod.py         # GIF → VOD 영상 삽입 샘플 (FFmpeg)
│   ├── test_festival_match.py      # E2E 매칭 검증
│   ├── test_festival_api.py        # 축제 API 테스트
│   ├── check_keyword_scenes.py     # 키워드 장면 점검
│   ├── check_region_detail.py      # 지역 상세 점검
│   ├── check_regions.py            # 지역 점검
│   ├── check_vod_smry.py           # VOD smry 점검
│   └── find_clean_food_frame.py    # 음식 클린 프레임 탐색
├── tests/              ← pytest
│   └── test_normalizer.py
├── templates/          ← 팝업 HTML + 배경 사진
│   ├── popup_*.html              # 축제 팝업 광고 HTML (가로형 520x300)
│   └── images/                   # 축제 배경 사진 6장
├── config/
│   └── channels.yaml             # 채널 설정
├── data/               ← (gitignore)
└── docs/
    ├── DB_LOAD_REQUEST.md        # DDL + parquet 적재 요청서
    ├── plans/                    # PLAN_01(OUTDATED) ~ PLAN_04
    └── reports/                  # 세션 리포트 + 매칭 결과
```

**`Shopping_Ad/` 루트에 `.py` 직접 생성 금지.**

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` Shopping_Ad 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.detected_object_yolo` | `vod_id_fk`, `frame_ts`, `label`, `confidence`, `bbox` | VARCHAR(64)/REAL/VARCHAR(64)/REAL/REAL[] | YOLO 탐지 결과 |
| `public.detected_object_clip` | `vod_id_fk`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | VARCHAR(64)/REAL/VARCHAR(200)/REAL/VARCHAR(32)/BOOLEAN | CLIP 개념 태깅 |
| `public.detected_object_stt` | `vod_id_fk`, `start_ts`, `end_ts`, `keyword`, `ad_category`, `ad_hints` | VARCHAR(64)/REAL/REAL/VARCHAR(100)/VARCHAR(32)/TEXT | STT 키워드 |
| `public.vod` | `full_asset_id`, `asset_nm` | VARCHAR(64)/VARCHAR(255) | VOD 메타데이터 |
| `public.vod` | `smry` | TEXT | 지역/음식 키워드 추출 (매칭 보강) |
| `public.seasonal_market` | `product_name`, `broadcast_date`, `start_time`, `end_time`, `channel` | VARCHAR(200)/DATE/TIME/TIME/VARCHAR(32) | 제철장터 편성 매칭 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `public.seasonal_market` | `product_name`, `broadcast_date`, `start_time`, `end_time`, `channel` | 각종 | 제철장터 편성 크롤링 적재 |
| `serving.shopping_ad` | `vod_id_fk` | VARCHAR(64) | FK → vod.full_asset_id |
| `serving.shopping_ad` | `ts_start`, `ts_end` | REAL | 광고 노출 타임스탬프 |
| `serving.shopping_ad` | `ad_category` | VARCHAR(32) | `관광지` / `음식` |
| `serving.shopping_ad` | `signal_source` | VARCHAR(32) | `stt` / `clip` / `yolo` / `ocr` |
| `serving.shopping_ad` | `score` | REAL | 매칭 스코어 |
| `serving.shopping_ad` | `ad_hints` | TEXT | 매칭 근거 키워드 |
| `serving.shopping_ad` | `ad_action_type` | VARCHAR(32) | `local_gov_popup` / `seasonal_market` |
| `serving.shopping_ad` | `ad_image_url` | TEXT | 팝업 GIF URL |
| `serving.shopping_ad` | `product_name` | VARCHAR(200) | 축제명 또는 상품명 |
| `serving.shopping_ad` | `channel` | VARCHAR(32) | 제철장터 채널명 |

---

## 현재 상태 (2026-04-01)

| 항목 | 상태 |
|------|------|
| Visit Korea 축제 크롤러 | 완료 (63건/50지역) |
| 제철장터 크롤러 | 완료 (재크롤링 필요 — 발표 전) |
| 통합 매칭 파이프라인 | 완료 (축제 6건 + 제철장터 4건) |
| 축제 팝업 GIF 생성 | 완료 (63건) |
| DB 적재 | 완료 (타이밍 수정분 재적재 요청 중) |
| PLAN_01 2건 | OUTDATED (홈쇼핑 전략 → 폐기) |

---

## 협업 규칙

- `main` 직접 Push 금지 — PR 필수
- Object_Detection parquet 스키마 변경 시 인터페이스 업데이트
- 발표 전 제철장터 재크롤링 필요

---

**마지막 수정**: 2026-04-01
**프로젝트 상태**: 파이프라인 구현 완료, DB 재적재 대기
