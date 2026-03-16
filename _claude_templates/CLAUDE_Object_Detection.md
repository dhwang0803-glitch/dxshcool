# Object_Detection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

VOD 영상 프레임에서 **YOLOv8 배치 사전 분석**을 수행한다.
감지된 객체(레이블, 신뢰도, 바운딩박스)를 **로컬 parquet 파일**로 저장하고,
Shopping_Ad 모듈이 이를 소비하여 홈쇼핑 광고 매칭에 사용한다.

> **실시간 아님**: 모든 VOD를 사전에 배치 분석하여 parquet로 저장하는 방식.
> VPC에는 적재하지 않는다 (VPC는 thin serving layer).

## 파일 위치 규칙 (MANDATORY)

```
Object_Detection/
├── src/       ← import 전용 라이브러리 (직접 실행 X)
├── scripts/   ← 직접 실행 스크립트 (python scripts/xxx.py)
├── tests/     ← pytest
├── config/    ← 모델 설정, 신뢰도 임계값 yaml
└── docs/      ← 탐지 정확도 리포트
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| YOLO 모델 로드 및 추론 | `src/detector.py` |
| 프레임 추출 유틸 | `src/frame_extractor.py` |
| 탐지 결과 parquet 저장 | `src/parquet_writer.py` |
| VOD 배치 사전 분석 | `scripts/batch_detect.py` |
| pytest | `tests/` |
| 모델/임계값 설정 | `config/detection_config.yaml` |

**`Object_Detection/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
from ultralytics import YOLO   # YOLOv8n (속도) / YOLOv8x (정확도)
import cv2                     # 프레임 추출
import torch
import pandas as pd            # parquet 저장
import pyarrow                 # parquet I/O
```

- 모델: YOLOv8n (속도 우선) 또는 YOLOv8x (정확도 우선)
- 신뢰도 임계값: 0.5 (config에서 조정)
- 출력: `data/vod_detected_object.parquet` (로컬 전용)

## 탐지 파이프라인

```
VOD 영상 파일
    → 프레임 추출 (N fps 샘플링)
    → YOLOv8 배치 추론 (로컬 GPU/CPU)
    → 신뢰도 필터링 (>= 0.5)
    → vod_detected_object.parquet 저장 (로컬)
    → Shopping_Ad가 parquet 소비
```

## 산출물 스펙

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | VARCHAR(64) | VOD 식별자 (`vod.full_asset_id`) |
| `frame_ts` | FLOAT | 프레임 타임스탬프 (초) |
| `label` | VARCHAR | YOLO 클래스명 (`person`, `chair`, `couch` 등) |
| `confidence` | FLOAT | 신뢰도 (0.0~1.0) |
| `bbox` | TEXT/JSON | 바운딩박스 좌표 `[x1, y1, x2, y2]` |

## 인터페이스

### 업스트림 (읽기)

| 소스 | 용도 |
|------|------|
| VOD 영상 파일 (로컬) | YOLO 추론 입력 |
| `public.vod` (`full_asset_id`) | VOD 식별 |

### 다운스트림 (쓰기)

| 산출물 | 위치 | 소비자 |
|--------|------|--------|
| `data/vod_detected_object.parquet` | 로컬 | Shopping_Ad |

> **VPC 미적재**: 탐지 원시 데이터는 로컬에만 보관. VPC에는 Shopping_Ad가 최종 매칭 결과(`serving.shopping_ad`)만 적재.

## ⚠️ 인프라 제약

- VPC: 1 core / 1GB RAM (+3GB swap) / 150GB Storage
- 모든 YOLO 추론은 **로컬 머신**에서 수행
- parquet 파일은 로컬 `data/` 디렉토리에 저장 (Git 제외)
