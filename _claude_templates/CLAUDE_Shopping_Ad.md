# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

Object_Detection 산출물(`vod_detected_object.parquet`) + TV 시간표(EPG) + 홈쇼핑 상품 카탈로그를 연동하여
**홈쇼핑 광고 팝업 데이터**를 생성하고 VPC `serving.shopping_ad` 테이블에 적재한다.

시청자가 TV를 보는 중 화면에 보이는 상품과 유사한 홈쇼핑 상품을
팝업으로 노출하고, 채널 이동 또는 시청예약 액션을 제공한다.

> **비즈니스 로직 소유**: YOLO 클래스(`chair`, `couch`)를 상품 카테고리(`소파`)로 해석하는 매핑은
> 탐지가 아닌 비즈니스 로직이므로 이 브랜치가 `product_object_mapping`을 소유한다.

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 매핑 테이블, EPG 소스 설정 yaml
└── docs/      ← 광고 로직 설계 문서
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| EPG 파서 | `src/epg_parser.py` |
| YOLO 클래스 → 상품 카테고리 매핑 | `src/product_mapper.py` |
| 팝업 메시지 빌더 | `src/popup_builder.py` |
| VPC serving 테이블 적재 | `src/serving_writer.py` |
| EPG 동기화 스크립트 | `scripts/run_epg_sync.py` |
| 광고 매칭 파이프라인 실행 | `scripts/run_ad_pipeline.py` |
| serving 테이블 적재 스크립트 | `scripts/export_to_serving.py` |
| pytest | `tests/` |
| EPG 소스/매핑 설정 | `config/ad_config.yaml` |

**`Shopping_Ad/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import requests           # EPG API 호출
import pandas as pd       # parquet 읽기, 매칭 로직
import psycopg2           # VPC serving 테이블 적재
from dotenv import load_dotenv
```

## 테이블 소유

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `tv_schedule` | 로컬 DB/parquet | EPG 기반 TV 시간표 (채널, 시간, 프로그램) |
| `homeshopping_product` | 로컬 DB/parquet | 홈쇼핑 상품 카탈로그 (상품명, 카테고리, 가격) |
| `product_object_mapping` | 로컬 DB/parquet | YOLO 클래스 → 상품 카테고리 매핑 |
| `serving.shopping_ad` | **VPC** | 최종 광고 팝업 데이터 (API_Server 직접 조회) |

## 광고 매칭 파이프라인

```
vod_detected_object.parquet (Object_Detection 산출물)
    → product_object_mapping (YOLO label → 상품 카테고리)
    → homeshopping_product (카테고리 매칭 → 후보 상품)
    → tv_schedule (현재 홈쇼핑 채널 방영 확인)
    → serving.shopping_ad (VPC 적재 — 팝업 데이터)
    → API_Server /ad/popup → Frontend 팝업 오버레이
```

## 팝업 메시지 스펙

```json
{
  "trigger_label": "소파",
  "product_name": "시몬스 3인용 패브릭 소파",
  "channel": "GS샵",
  "price": "299,000원",
  "actions": ["채널이동", "시청예약"]
}
```

## 인터페이스

### 업스트림 (읽기)

| 소스 | 타입 | 용도 |
|------|------|------|
| `vod_detected_object.parquet` | 로컬 파일 | Object_Detection 산출물 (YOLO 탐지 결과) |
| `public.vod` | VPC DB | VOD 메타데이터 (asset_nm 등) |

### 다운스트림 (쓰기)

| 테이블 | 위치 | 비고 |
|--------|------|------|
| `tv_schedule` | 로컬 | EPG 파싱 결과 |
| `homeshopping_product` | 로컬 | 상품 카탈로그 |
| `product_object_mapping` | 로컬 | YOLO → 상품 카테고리 매핑 |
| `serving.shopping_ad` | **VPC** | ON CONFLICT (vod_id, product_id) DO UPDATE |

## ⚠️ 인프라 제약

- VPC: 1 core / 1GB RAM (+3GB swap) / 150GB Storage → **thin serving layer**
- 모든 매칭 연산은 **로컬 머신**에서 수행
- VPC에는 `serving.shopping_ad` 최종 결과만 적재 (API_Server가 직접 조회)
- 로컬 테이블(tv_schedule, homeshopping_product, product_object_mapping)은 VPC 미적재
