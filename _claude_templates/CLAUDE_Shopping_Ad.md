# Shopping_Ad — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**VOD 장면 인식 기반 지자체 광고 팝업 + 제철장터 채널 연계**

> **2026-03-19 방향 전환**: 홈쇼핑 연동 폐기 → 지자체 광고 + 제철장터 연계로 전환.

Object_Detection의 사물인식 결과(CLIP/STT/YOLO)를 소비하여,
**관광지/지역** 인식 시 지자체 광고 팝업을, **음식** 인식 시 제철장터 채널 연계를 트리거한다.

> **비즈니스 로직 소유**: 인식 결과 → 광고 카테고리 매핑, 트리거 조건은 이 브랜치가 소유한다.

## 파일 위치 규칙 (MANDATORY)

```
Shopping_Ad/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 매핑 테이블, 크롤링 설정 yaml
└── docs/      ← 광고 로직 설계 문서
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 제철장터 크롤러 (seasonal_market 수집) | `src/crawlers/lg_hellovision.py` |
| YOLO 클래스 → 광고 카테고리 매핑 | `src/product_mapper.py` |
| 팝업 메시지 빌더 | `src/popup_builder.py` |
| VPC serving 테이블 적재 | `src/serving_writer.py` |
| 크롤링 실행 스크립트 | `scripts/crawl_products.py` |
| 광고 매칭 파이프라인 실행 | `scripts/run_shopping_ad.py` |
| serving 테이블 적재 스크립트 | `scripts/ingest_to_db.py` |
| pytest | `tests/` |
| 크롤링/매핑 설정 | `config/channels.yaml`, `config/ad_config.yaml` |

**`Shopping_Ad/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
import pandas as pd       # parquet 읽기, 매칭 로직
import psycopg2           # VPC serving 테이블 적재
from dotenv import load_dotenv
from playwright.async_api import async_playwright  # 제철장터 크롤링
import pyarrow            # parquet I/O
import yaml               # 설정 파일
```

## 테이블 소유

| 테이블 | 위치 | 설명 |
|--------|------|------|
| `seasonal_market` | 로컬 DB | 제철장터 채널 편성표 (LG헬로비전 크롤링) |
| `product_object_mapping` | 로컬 (yaml/CSV) | YOLO 클래스 / CLIP 개념 → 광고 카테고리 매핑 |
| `serving.shopping_ad` | **VPC** | 트리거 포인트 + 광고 액션 (API_Server 직접 조회) |

## 인터페이스

### 업스트림 (읽기)

| 소스 | 타입 | 용도 |
|------|------|------|
| `vod_detected_object.parquet` | 로컬 파일 | Object_Detection 산출물 (YOLO 탐지 결과) |
| `vod_clip_concept.parquet` | 로컬 파일 | CLIP 개념 태깅 |
| `vod_stt_concept.parquet` | 로컬 파일 | STT 키워드 |
| `public.vod` | VPC DB | VOD 메타데이터 (asset_nm, genre 등) |
| `public.seasonal_market` | DB | 제철장터 편성표 (음식 인식 시 매칭) |

### 다운스트림 (쓰기)

| 테이블 | 위치 | 비고 |
|--------|------|------|
| `seasonal_market` | 로컬 DB | 크롤링 UPSERT |
| `product_object_mapping` | 로컬 | YOLO → 광고 카테고리 매핑 |
| `serving.shopping_ad` | **VPC** | 지자체 광고 + 제철장터 채널 연계 서빙 |

## ⚠️ 인프라 제약

- VPC: 1 core / 1GB RAM (+3GB swap) / 150GB Storage → **thin serving layer**
- 모든 매칭 연산은 **로컬 머신**에서 수행
- VPC에는 `serving.shopping_ad` 최종 결과만 적재 (API_Server가 직접 조회)
- 로컬 테이블(seasonal_market, product_object_mapping)은 VPC 미적재
