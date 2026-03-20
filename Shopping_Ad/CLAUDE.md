# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.
>
> ⚠️ **전략 변경 (2026-03-19)**: 홈쇼핑 매칭 폐기 → **제철장터(음식) + 지자체 광고(관광지)** 2종.
> 아래 데이터 플로우는 이전 홈쇼핑 기준. 현재 구현: `src/festival_matcher.py` + Visit Korea 축제 크롤링.

---

## 모듈 역할

**VOD 세부장르 기반 트리거 포인트 추출 + 홈쇼핑 tv_schedule 매칭 → 광고 팝업 적재**

VOD_Embedding의 세부장르 분류 결과와 Object_Detection의 사물인식 parquet을 소비하여,
장르별 조건에 맞는 장면(time_sec)을 트리거 포인트로 추출하고
매일 자정 수집한 tv_schedule(홈쇼핑 상품·판매시간)과 매칭하여
`serving.shopping_ad`에 적재한다.
시청자가 VOD를 재생하면 API_Server가 트리거 포인트 도달 시점에 팝업을 발화한다.

> **비즈니스 로직 소유**: 세부장르별 트리거 조건, 사물 → 상품 카테고리 매핑(`product_object_mapping`)은
> 탐지가 아닌 비즈니스 로직이므로 이 브랜치가 소유한다.

### 데이터 플로우

```
━━━ 배치 처리 (사전 계산) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[VOD_Embedding]
  vod_embedding 결과 → 예능 VOD 세부장르 분류
  세부장르: 여행 / 먹방·음식 / 토크쇼
  → public.vod.genre 컬럼 (또는 별도 분류 테이블)

[Object_Detection]
  vod_detected_object.parquet   ← YOLO bbox 탐지 결과
  vod_clip_concept.parquet      ← CLIP 개념 태깅 (context_valid 포함)
  vod_stt_concept.parquet       ← Whisper STT 키워드

[Shopping_Ad — 트리거 포인트 추출]
  세부장르별 조건 적용:
    먹방·음식 → 음식 인서트 컷 / 출연자 식사 장면 (time_sec)
    여행      → 지역 음식·특산품 등장 장면 (time_sec)
    토크쇼    → 상품 언급 STT 키워드 구간 (time_sec)
  → trigger_point 후보 목록 (vod_id + time_sec + genre + ad_category)
  → serving.shopping_ad 에 적재 (product 정보는 미확정 상태)

━━━ 매일 자정 (tv_schedule 갱신) ━━━━━━━━━━━━━━━━━━━━━━━━━

  홈쇼핑 채널 편성 API 수집
  → tv_schedule 갱신 (상품명, 카테고리, 방송 시작·종료 시간, 채널)
  → ad_category 기준으로 serving.shopping_ad 의 product 정보 업데이트

━━━ 실시간 (시청자 재생 시작) ━━━━━━━━━━━━━━━━━━━━━━━━━━━

  시청자 VOD 재생 시작
  → API_Server: 해당 vod_id 의 serving.shopping_ad 조회
  → 재생 중 trigger_ts(time_sec) 도달 순간
  → 매칭된 홈쇼핑 상품 팝업 발화
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
| `tv_schedule` | 로컬 DB | 홈쇼핑 채널 상품 편성표 (상품명, 카테고리, 판매 시작·종료 시간, 채널) — **매일 자정 갱신** |
| `homeshopping_product` | 로컬 DB/CSV | 홈쇼핑 상품 카탈로그 (상품명, 카테고리, 가격) — 이 브랜치가 수집·보유 |
| `product_object_mapping` | 로컬 (yaml/CSV) | YOLO 클래스 / CLIP 개념 → 광고 카테고리 매핑 |
| `serving.shopping_ad` | **VPC** | 트리거 포인트 + 매칭 상품 (API_Server 직접 조회) |

---

## 세부장르별 트리거 조건

| 세부장르 | 트리거 장면 | 탐지 신호 |
|---------|-----------|---------|
| 먹방·음식 | 음식 인서트 컷, 출연자 식사 장면 | YOLO(`food`, `bowl` 등) + CLIP(음식 개념) |
| 여행 | 지역 음식·특산품 등장 장면 | CLIP(지역 음식 개념) + STT(지역명) |
| 토크쇼 | 상품·브랜드 언급 구간 | STT 키워드 우선 |

**중복 제거 규칙**
- 동일 `vod_id` + 동일 `ad_category`: 신뢰도 상위 1건만
- 동일 카테고리 트리거 간 최소 간격: 60초

---

## 팝업 메시지 스펙

```json
{
  "trigger_label": "소파",
  "product_name": "시몬스 3인용 패브릭 소파",
  "channel": "GS샵",
  "price": "299,000원",
  "signal_source": "clip",
  "score": 0.82,
  "actions": ["채널이동", "시청예약"]
}
```

---

## 구현 단계 (PLAN 요약)

### Phase 1 — 트리거 포인트 추출 (`src/trigger_extractor.py`)
- 세부장르 분류 결과 + 3종 parquet → 장르별 조건 적용 → `trigger_ts(time_sec)` 목록 생성
- 산출물: `data/trigger_points.parquet` (vod_id, time_sec, genre, ad_category, score)
- 완료 기준: `serving.shopping_ad` 스키마 확정 전 로컬 출력만 구현

### Phase 2 — tv_schedule 수집 (`scripts/run_epg_sync.py`)
- 매일 자정 홈쇼핑 채널 편성 API 수집 → `tv_schedule` 갱신
```bash
python scripts/run_epg_sync.py   # 수동 실행 또는 cron 등록
```

### Phase 3 — 매칭 + VPC 적재 (`scripts/run_shopping_ad.py`)
- trigger_points + tv_schedule 매칭 → serving.shopping_ad 적재
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
| `vod_detected_object.parquet` | `vod_id`, `frame_ts`, `label`, `confidence`, `bbox` | str/float/str/float/list | YOLO 탐지 결과 — 트리거 조건 적용 대상 |
| `vod_clip_concept.parquet` | `vod_id`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | str/float/str/float/str/bool | CLIP 개념 태깅 |
| `vod_stt_concept.parquet` | `vod_id`, `start_ts`, `end_ts`, `keyword`, `ad_category`, `ad_hints` | str/float/float/str/str/list | STT 키워드 |
| `public.vod` | `full_asset_id`, `asset_nm`, `genre` | VARCHAR(64), VARCHAR, VARCHAR | VOD 메타데이터 + **세부장르** (VOD_Embedding 분류 결과) |

### 다운스트림 (쓰기)

| 대상 | 컬럼 | 타입 | 비고 |
|------|------|------|------|
| `serving.shopping_ad` (VPC) | `vod_id`, `trigger_ts`, `genre`, `ad_category`, `product_nm`, `channel`, `air_start`, `air_end`, `signal_source`, `score` | str/float/str/str/str/str/time/time/str/float | ON CONFLICT (vod_id, trigger_ts) DO UPDATE — **스키마 Database_Design과 협의 필요** |
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
| `serving.shopping_ad` 스키마 | Database_Design | 🔲 협의 필요 |
| `public.vod.genre` 컬럼 추가 | Database_Design + VOD_Embedding | 🔲 세부장르 분류 완료 후 적재 |
| 홈쇼핑 편성 API 소스 확정 | Shopping_Ad | 🔲 수집 대상 채널·API 확보 필요 |
| `homeshopping_product` 데이터 수집 | Shopping_Ad | 🔲 상품 카탈로그 확보 필요 |
| API_Server `/ad/popup` trigger_ts 기반 발화 연동 | API_Server (PLAN_06) | 🔲 serving.shopping_ad 완료 후 |

---

## 협업 규칙

- `main` 브랜치 직접 Push 금지 — 반드시 PR
- Object_Detection parquet 스키마 변경 시 인터페이스 섹션 즉시 업데이트
- `serving.shopping_ad` 스키마 확정 전까지 VPC 직접 적재 구현 보류
- PR description 필수 항목:
  1. **변경사항 요약**
  2. **사후영향 평가**: `agents/IMPACT_ASSESSOR.md` 실행 결과
  3. **보안 점검 보고서**: `agents/SECURITY_AUDITOR.md` 실행 결과
