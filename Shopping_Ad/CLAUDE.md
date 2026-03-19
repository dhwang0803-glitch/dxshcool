# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

---

## 모듈 역할

**VOD 장면 인식 기반 지자체 광고 팝업 + 제철장터 채널 연계**

> **2026-03-19 방향 전환**: 홈쇼핑 연동 폐기 → 지자체 광고 + 제철장터 연계로 전환.

Object_Detection의 사물인식 결과(CLIP/STT/YOLO)를 소비하여,
**관광지/지역** 인식 시 지자체 광고 팝업을, **음식** 인식 시 제철장터 채널 연계를 트리거한다.

| 인식 대상 | 광고 액션 | 예시 |
|----------|---------|------|
| 관광지/지역 (진주, 여수 등) | 지자체 광고 팝업 (생성형 AI 제작, OCI 저장) | 진주 동물축제 광고 등 |
| 음식 (삼겹살, 한우 등) | 제철장터 채널 상품 연계 (채널 이동/시청예약) | 한우 축제, 김치 축제 등 |

> **비즈니스 로직 소유**: 인식 결과 → 광고 카테고리 매핑, 트리거 조건은 이 브랜치가 소유한다.

### 데이터 플로우

```
━━━ 배치 처리 (사전 계산) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Object_Detection]
  vod_detected_object.parquet   ← YOLO bbox 탐지 결과
  vod_clip_concept.parquet      ← CLIP 개념 태깅 (context_valid 포함)
  vod_stt_concept.parquet       ← Whisper STT 키워드

[Shopping_Ad — 트리거 포인트 추출]
  인식 대상별 조건 적용:
    관광지/지역 → STT 지역명 + CLIP 지역 개념 → 지자체 광고 팝업
    음식        → YOLO 음식 bbox + CLIP 음식 개념 → 제철장터 채널 연계
  → trigger_point 후보 (vod_id + time_sec + ad_category + ad_action_type)
  → serving.shopping_ad 적재

━━━ 광고 소재 생성 (MVP: 수동/반자동) ━━━━━━━━━━━━━━━━━━━━━

  축제 리스트 수집 (예: 3~4월 지역 축제)
  → 생성형 AI로 팝업 광고 이미지 제작
  → OCI Object Storage 업로드
  → serving 테이블에 광고 이미지 URL 적재

━━━ 실시간 (시청자 재생 시작) ━━━━━━━━━━━━━━━━━━━━━━━━━━━

  시청자 VOD 재생 시작
  → API_Server: 해당 vod_id 의 serving.shopping_ad 조회
  → 재생 중 trigger_ts(time_sec) 도달 순간
  → 관광지/지역: 지자체 광고 팝업 표시
  → 음식: 제철장터 채널 이동/시청예약 안내
```

---

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/          ← import 전용 라이브러리 (직접 실행 X)
├── scripts/      ← 직접 실행 스크립트
├── tests/        ← pytest
├── config/       ← yaml 설정
├── docs/
│   ├── plans/    ← PLAN_0X 설계 문서
│   └── reports/  ← 세션 리포트
└── data/         ← 로컬 임시 데이터 (gitignore)
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 멀티모달 신호 통합 매칭 엔진 | `src/matcher.py` |
| YOLO 클래스 → 상품 카테고리 매핑 | `src/product_mapper.py` |
| EPG 파서 (tv_schedule 생성) | `src/epg_parser.py` |
| 팝업 메시지 빌더 | `src/popup_builder.py` |
| VPC serving 테이블 적재 | `src/serving_writer.py` |
| 배치 광고 매칭 파이프라인 | `scripts/run_shopping_ad.py` |
| EPG 동기화 스크립트 | `scripts/run_epg_sync.py` |
| VPC serving 적재 스크립트 | `scripts/ingest_to_db.py` |
| pytest | `tests/` |
| 카탈로그·EPG·매핑 설정 | `config/ad_config.yaml` |

**`Shopping_Ad/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

---

## 기술 스택

```python
import pandas as pd          # parquet 읽기, 매칭 로직
import requests              # EPG API 호출
import psycopg2              # VPC serving 테이블 적재
from dotenv import load_dotenv
import pyarrow               # parquet I/O
import yaml                  # 설정 파일
```

```bash
conda activate myenv
pip install pandas pyarrow psycopg2-binary pyyaml requests
```

---

## 테이블 소유

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `product_object_mapping` | 로컬 (yaml/CSV) | YOLO 클래스 / CLIP 개념 → 광고 카테고리 매핑 |
| `serving.shopping_ad` | **VPC** | 트리거 포인트 + 광고 액션 (API_Server 직접 조회) |
| ~~`tv_schedule`~~ | — | **제거**: 홈쇼핑 연동 폐기 (2026-03-19) |
| ~~`homeshopping_product`~~ | — | **미정**: 지역상품 카탈로그로 전환 여부 검토 중 |

---

## 인식 대상별 트리거 조건

| 인식 대상 | 트리거 장면 | 탐지 신호 | 광고 액션 |
|----------|-----------|---------|---------|
| 관광지/지역 | 지역명 언급, 지역 풍경 장면 | STT(지역명) + CLIP(지역 개념) | 지자체 광고 팝업 |
| 음식 | 음식 등장, 식사 장면, 음식명 언급 | YOLO(`food` 등) + CLIP(음식 개념) + STT(음식명) | 제철장터 채널 연계 |

**중복 제거 규칙**
- 동일 `vod_id` + 동일 `ad_category`: 신뢰도 상위 1건만
- 동일 카테고리 트리거 간 최소 간격: 60초

---

## 팝업 메시지 스펙

### 지자체 광고 팝업 (관광지/지역 인식 시)
```json
{
  "ad_type": "local_gov",
  "trigger_label": "진주",
  "ad_title": "진주 동물축제",
  "ad_image_url": "https://objectstorage.../jinju_festival.png",
  "signal_source": "stt",
  "score": 0.85,
  "actions": ["광고 보기"]
}
```

### 제철장터 채널 연계 (음식 인식 시)
```json
{
  "ad_type": "seasonal_market",
  "trigger_label": "삼겹살",
  "product_name": "제철장터 한우 특가",
  "channel": "제철장터",
  "signal_source": "clip",
  "score": 0.82,
  "actions": ["채널이동", "시청예약"]
}
```

---

## 구현 단계 (PLAN 요약)

### Phase 1 — 트리거 포인트 추출 (`src/trigger_extractor.py`)
- 3종 parquet → 인식 대상별 조건 적용 → `trigger_ts(time_sec)` 목록 생성
- 산출물: `data/trigger_points.parquet` (vod_id, time_sec, ad_category, ad_action_type, score)
- 완료 기준: 로컬 출력 확인

### Phase 2 — 광고 소재 생성 (MVP)
- 축제 리스트 수집 (예: 3~4월 지역 축제)
- 생성형 AI로 팝업 광고 이미지 제작 → OCI 업로드
- serving 테이블에 광고 이미지 URL 적재

### Phase 3 — 매칭 + VPC 적재 (`scripts/run_shopping_ad.py`)
- trigger_points + 광고 소재 매칭 → serving.shopping_ad 적재
```bash
python scripts/run_shopping_ad.py \
  --triggers  data/trigger_points.parquet \
  --output    data/shopping_ad_candidates.parquet

python scripts/ingest_to_db.py \
  --input data/shopping_ad_candidates.parquet
```

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트 (Rule 3).

### 업스트림 (읽기)

| 소스 | 핵심 컬럼 | 타입 | 용도 |
|------|----------|------|------|
| `vod_detected_object.parquet` | `vod_id`, `frame_ts`, `label`, `confidence`, `bbox` | str/float/str/float/list | YOLO 탐지 결과 소비 |
| `vod_clip_concept.parquet` | `vod_id`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | str/float/str/float/str/bool | CLIP 개념 소비 |
| `vod_stt_concept.parquet` | `vod_id`, `start_ts`, `end_ts`, `transcript`, `keyword`, `ad_category`, `ad_hints` | str/float/float/str/str/str/list | STT 키워드 소비 |
| `public.vod` | `full_asset_id`, `asset_nm`, `genre` | VARCHAR(64), VARCHAR(255), VARCHAR | VOD 메타데이터 + **세부장르** |
| `public.detected_object_yolo` | `vod_id_fk`, `frame_ts`, `label`, `confidence`, `bbox` | VARCHAR(64)/REAL/VARCHAR(64)/REAL/REAL[] | YOLO 탐지 DB 조회 |
| `public.detected_object_clip` | `vod_id_fk`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | VARCHAR(64)/REAL/VARCHAR(200)/REAL/VARCHAR(32)/BOOLEAN | CLIP 개념 DB 조회 |
| `public.detected_object_stt` | `vod_id_fk`, `start_ts`, `end_ts`, `keyword`, `ad_category`, `ad_hints` | VARCHAR(64)/REAL/REAL/VARCHAR(100)/VARCHAR(32)/TEXT | STT 키워드 DB 조회 |
| ~~`public.tv_schedule`~~ | — | — | **제거**: 홈쇼핑 연동 폐기 |
| ~~`public.homeshopping_product`~~ | — | — | **미정**: 지역상품 카탈로그로 전환 여부 검토 중 |

### 다운스트림 (쓰기)

| 대상 | 컬럼 | 타입 | 비고 |
|------|------|------|------|
| `serving.shopping_ad` | `vod_id_fk` | VARCHAR(64) | FK → vod (ON DELETE CASCADE) |
| `serving.shopping_ad` | `ts_start`, `ts_end` | REAL | 트리거 구간 (초), CHECK ts_end >= ts_start |
| `serving.shopping_ad` | `ad_category` | VARCHAR(32) | 한식, 지방특산물, 여행지 등 |
| `serving.shopping_ad` | `signal_source` | VARCHAR(16) | CHECK IN ('stt','clip','yolo') |
| `serving.shopping_ad` | `score` | REAL | 0.0~1.0 매칭 신뢰도 |
| `serving.shopping_ad` | `ad_hints` | TEXT | JSON 배열 (지역 힌트) |
| `serving.shopping_ad` | `ad_action_type` | VARCHAR(32) | `'local_gov_popup'` / `'seasonal_market'` |
| `serving.shopping_ad` | `ad_image_url` | TEXT | 지자체 광고 이미지 URL (OCI) |
| `serving.shopping_ad` | `product_name` | VARCHAR(200) | 제철장터 상품명 (음식 인식 시) |
| `serving.shopping_ad` | `channel` | VARCHAR(32) | 연계 채널명 (제철장터 등) |
| `serving.shopping_ad` | `expires_at` | TIMESTAMPTZ | TTL 30일 (DEFAULT NOW() + 30d) |
| ~~`public.homeshopping_product`~~ | — | — | **제거**: 홈쇼핑 크롤링 폐기 |
| `data/trigger_points.parquet` (로컬) | `vod_id`, `time_sec`, `genre`, `ad_category`, `score` | - | Phase 1 중간 검증용 |
| `data/shopping_ad_candidates.parquet` (로컬) | serving.shopping_ad 컬럼 동일 | - | Phase 3 VPC 적재 전 검증용 |

---

## ⚠️ 인프라 제약

- VPC: 1 core / 1GB RAM (+3GB swap) / 150GB Storage → **thin serving layer**
- **모든 매칭 연산은 로컬 머신에서 수행**
- VPC에는 `serving.shopping_ad` 최종 결과만 적재
- 로컬 테이블(tv_schedule, homeshopping_product, product_object_mapping)은 VPC 미적재

---

## TDD 개발 워크플로우

```
1. Security Audit (Phase 시작 전)      → agents/SECURITY_AUDITOR.md
2. PLAN 읽기                           → docs/plans/PLAN_0X_*.md
3. Test Writer → 테스트 작성 (Red)     → agents/TEST_WRITER.md
4. Developer → 구현 (Green)            → agents/DEVELOPER.md
5. Tester → 테스트 실행                → agents/TESTER.md
   └── FAIL: Developer 재호출 (최대 3회)
6. Refactor → 코드 품질                → agents/REFACTOR.md
7. Reporter → 보고서 작성              → agents/REPORTER.md
8. Security Audit (커밋 직전)          → agents/SECURITY_AUDITOR.md
9. git commit / push / PR
```

---

## 의존성 및 협의 필요 항목

| 항목 | 담당 | 현황 |
|------|------|------|
| `serving.shopping_ad` 스키마 재설계 | Database_Design | 🔲 지자체 광고 + 제철장터 반영 필요 |
| 축제 리스트 수집 + 광고 소재 생성 파이프라인 | Shopping_Ad | 🔲 MVP 설계 필요 |
| 제철장터 채널 연계 방식 확정 | Shopping_Ad | 🔲 채널 이동/시청예약 UX 설계 |
| `homeshopping_product` → 지역상품 카탈로그 전환 여부 | Shopping_Ad + Database_Design | 🔲 필요성 검토 중 |
| API_Server `/ad/popup` trigger_ts 기반 발화 연동 | API_Server (PLAN_06) | 🔲 serving.shopping_ad 완료 후 |

---

## 협업 규칙

- `main` 브랜치 직접 Push 금지 — 반드시 PR
- Object_Detection parquet 스키마 변경 시 이 파일 인터페이스 섹션 업데이트
- `serving.shopping_ad` 스키마 확정 완료 — DB 적재 구현 가능
- PR description 필수 항목:
  1. **변경사항 요약**
  2. **사후영향 평가**: `agents/IMPACT_ASSESSOR.md` 실행 결과
  3. **보안 점검 보고서**: `agents/SECURITY_AUDITOR.md` 실행 결과
