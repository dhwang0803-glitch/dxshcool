# Object_Detection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

TV 방송/VOD 영상 프레임에서 **실시간 사물인식**을 수행한다.
감지된 객체(레이블, 신뢰도, 바운딩박스)를 DB에 저장하고,
Shopping_Ad 모듈이 이를 소비하여 홈쇼핑 광고 팝업을 생성한다.

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
| 모델 로드 및 추론 로직 | `src/detector.py` |
| 프레임 추출 유틸 | `src/frame_extractor.py` |
| 탐지 결과 DB 저장 | `src/db_writer.py` |
| 실시간 탐지 실행 | `scripts/run_detection.py` |
| VOD 배치 처리 | `scripts/batch_process.py` |
| pytest | `tests/` |
| 모델/임계값 설정 | `config/detection_config.yaml` |

**`Object_Detection/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

## 기술 스택

```python
from ultralytics import YOLO   # YOLOv8
import cv2                     # 프레임 추출
import torch
import psycopg2                # detected_objects 테이블 저장
```

- 모델: YOLOv8n (실시간) 또는 YOLOv8x (정확도 우선)
- 신뢰도 임계값: 0.5 (config에서 조정)
- 출력 테이블: `detected_objects(frame_ts, label, confidence, bbox)`

## 탐지 파이프라인

```
영상 입력 (실시간 스트림 or 파일)
    → 프레임 추출 (N fps)
    → YOLO 추론
    → 신뢰도 필터링 (>= 0.5)
    → detected_objects 테이블 저장
    → Shopping_Ad 소비
```

## 인터페이스

- **업스트림**: TV 스트림 URL 또는 VOD 파일 경로
- **다운스트림**: `Shopping_Ad` — detected_objects 테이블을 폴링하여 광고 트리거
