# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

---

## 모듈 역할

**Object_Detection 산출물 소비 → 제철장터 상품 매칭 + 지자체 광고 연계 → `serving.shopping_ad` 적재**

Object_Detection이 추출한 VOD별 ad_category(음식/관광지) + region(지역명)을 기반으로,
음식 카테고리는 제철장터 채널 상품과 연계하고,
관광지 카테고리는 지자체 축제/관광 팝업 광고를 생성하여
`serving.shopping_ad`에 적재한다.

### 광고 2종 (2026-03-19 전략 확정)

| 카테고리 | 트리거 | 광고 액션 | 예시 |
|---------|--------|-----------|------|
| **음식** | YOLO+STT+CLIP+OCR "삼겹살" 탐지 | 제철장터 채널 상품 연계 (채널 이동/시청예약) | "국내산 삼겹살 — 제철장터" |
| **관광지/지역** | STT+OCR "순천" 탐지 | 지자체 광고 팝업 (축제·관광) | "경주 대릉원돌담길 축제 안내" |

> **대상 VOD**: `genre_detail IN ('여행', '음식_먹방')` — 2,958건
> **홈쇼핑 매칭 폐기** (2026-03-19) — 기존 `src/crawlers/` 코드 잔존하지만 미사용

### 데이터 플로우

```
━━━ 1회 사전 준비 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Visit Korea 축제 크롤링]
  scripts/crawl_festivals.py → data/region_festivals.yaml
  4~5월 축제 63건 / 50개 지역 (2026년)

[제철장터 편성표] (예정)
  → seasonal_market 테이블 또는 yaml

━━━ Object_Detection 배치 결과 소비 ━━━━━━━━━━━━━━━━━━━━━━

[Object_Detection 산출물]
  vod_detected_object.parquet  ← YOLO (best.pt 한식 71종)
  vod_clip_concept.parquet     ← CLIP 장면 분류
  vod_stt_concept.parquet      ← STT 키워드 (639개)
  vod_ocr_concept.parquet      ← OCR 자막 (bbox 포함)
  vod_ad_summary.parquet       ← VOD별 ad_category + region + trigger_count

━━━ Shopping_Ad 매칭 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[관광지 매칭]
  vod_ad_summary.region → region_festivals.yaml 조회
  → festival_matcher.py: 해당 지역 축제 연결
  → 팝업 생성: "📍 경주 축제 안내 — 대릉원돌담길 축제 04.03~04.05"
  → serving.shopping_ad 적재 (ad_action_type = 'local_gov_popup')

[음식 매칭] (예정)
  vod_ad_summary.ad_category = '음식'
  → stt_keywords.yaml의 ad_hints에서 제철장터 상품 연결
  → serving.shopping_ad 적재 (ad_action_type = 'seasonal_market')

━━━ 실시간 서빙 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

시청자 VOD 재생
  → API_Server: serving.shopping_ad 조회 (vod_id_fk)
  → 음식 → "제철장터에서 OO 판매중" 팝업 (채널 이동/시청예약)
  → 관광지 → "OO 지역 축제 안내" 팝업 (지자체 광고)
```

---

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/              ← import 전용 라이브러리
│   ├── festival_matcher.py   ← region → 축제 매칭 엔진
│   ├── crawlers/             ← (레거시) 홈쇼핑 크롤러 — 미사용
│   ├── normalizer.py         ← (레거시) 상품명 정규화
│   └── db_writer.py          ← DB 적재 유틸
├── scripts/          ← 직접 실행 스크립트
│   ├── crawl_festivals.py    ← Visit Korea 축제 크롤링
│   └── test_festival_match.py ← E2E 매칭 검증
├── tests/            ← pytest
├── config/           ← yaml 설정
├── data/             ← 로컬 데이터 (gitignore)
│   ├── festivals.json        ← 축제 원본 데이터
│   └── region_festivals.yaml ← region→축제 매핑
└── docs/
    ├── plans/        ← PLAN 설계 문서
    └── reports/      ← 세션 리포트
```

**`Shopping_Ad/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

---

## 기술 스택

```python
import pandas as pd          # parquet 읽기
import requests              # Visit Korea API 호출
import psycopg2              # VPC serving 테이블 적재
import yaml                  # 설정/축제 데이터
from dotenv import load_dotenv
```

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` 참조 (Rule 1).

### 업스트림 (읽기)

| 소스 | 컬럼/항목 | 타입 | 용도 |
|------|----------|------|------|
| Object_Detection `vod_ad_summary.parquet` | `vod_id`, `ad_categories`, `ad_regions`, `trigger_count` | str/list/list/int | VOD별 광고 카테고리+지역 |
| Object_Detection `vod_stt_concept.parquet` | `keyword`, `ad_category`, `ad_hints` | str/str/str | 제철장터 상품 힌트 |
| `data/region_festivals.yaml` | region → festival list | yaml | 축제 매칭 |
| `public.seasonal_market` (예정) | `product_name`, `broadcast_date`, `channel` | VARCHAR/DATE/VARCHAR | 제철장터 상품 |

### 다운스트림 (쓰기)

| 대상 | 컬럼 | 타입 | 비고 |
|------|------|------|------|
| `serving.shopping_ad` | `vod_id_fk` | VARCHAR(64) | FK → vod |
| | `ts_start`, `ts_end` | REAL | 트리거 구간 |
| | `ad_category` | VARCHAR(32) | "음식" / "관광지" |
| | `signal_source` | VARCHAR(16) | "stt" / "clip" / "yolo" / "ocr" |
| | `score` | REAL | 매칭 신뢰도 |
| | `ad_hints` | TEXT | 축제/상품 정보 JSON |
| | `ad_action_type` | VARCHAR(32) | "local_gov_popup" / "seasonal_market" |
| | `product_name` | VARCHAR(200) | 제철장터 상품명 (관광지면 NULL) |
| | `channel` | VARCHAR(32) | "제철장터" 등 |

---

## 현재 진행 상태

| 항목 | 상태 | 비고 |
|------|------|------|
| Visit Korea 축제 크롤러 | ✅ 완료 | 4~5월 63건/50지역 |
| festival_matcher (관광지→축제) | ✅ 완료 | E2E 7/17 매칭 검증 |
| 제철장터 매칭 (음식→상품) | 🔲 예정 | ad_hints 기반 |
| serving.shopping_ad 적재 | 🔲 예정 | DB 테이블 생성 대기 (조장) |
| 축제 없는 지역 일반 관광 팝업 | 🔲 예정 | 외부 축제 DB 추가 수집 시 확장 |

---

## 협업 규칙

- `main` 브랜치에 직접 Push 금지 — 반드시 Pull Request
- Object_Detection parquet 스키마 변경 시 인터페이스 섹션 업데이트
- PR description 필수 항목:
  1. **변경사항 요약**
  2. **사후영향 평가**
  3. **보안 점검 보고서**
