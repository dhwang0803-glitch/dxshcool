# Object_Detection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**YOLOv11 기반 VOD 배치 사물인식** — VOD 영상 프레임을 로컬에서 일괄 추론하여
`vod_detected_object.parquet`을 생성한다. Shopping_Ad가 이 파일을 소비한다.

> ⚠️ **로컬 전용 파이프라인**: VPC 인프라 제약(1 core / 1GB RAM)으로 모든 연산은 로컬에서 수행.
> VPC에는 `detected_object_yolo`, `detected_object_clip`, `detected_object_stt` 3개 테이블에 적재.

### 데이터 플로우

```
VOD 영상 파일 (로컬 트레일러 5,726개)
    → 프레임 추출 (N fps 샘플링, frame_extractor.py)
    → YOLOv11 배치 추론 (로컬 GPU/CPU, detector.py)
    → CLIP zero-shot 개념 태깅 (clip_scorer.py)
    → context_filter 검증 (context_filter.py)
    → Whisper STT 키워드 추출 (stt_scorer.py)
    → 신뢰도 필터링 (>= 0.5)
    → vod_detected_object.parquet 저장 (로컬)
    → vod_clip_concept.parquet 저장 (로컬)
    → vod_stt_concept.parquet 저장 (로컬)
    → Shopping_Ad가 parquet 소비 → serving.shopping_ad 적재
    → [사전처리 완료 후 영상 파일 삭제 가능 — DB에는 타임스탬프+광고만 저장]
```

### UI 서빙 아키텍처

```
[사전 배치 처리 — 1회]
트레일러 로컬 처리 → serving.shopping_ad DB 적재 → 영상 파일 삭제 가능

[실시간 서빙]
UI 영상 재생 (HTML5 video / YouTube iframe)
  → currentTime 폴링 (0.5~1초)
  → API_Server: SELECT * FROM serving.shopping_ad
                WHERE vod_id=$1 AND ts_start <= $2 AND ts_end >= $2
  → 팝업 표시
```

### 산출물 스키마 (parquet)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 (`full_asset_id`) |
| `frame_ts` | float | 프레임 타임스탬프 (초) |
| `label` | str | YOLO 클래스명 (파인튜닝 후: 한식 71종+) |
| `confidence` | float | 신뢰도 (0.0~1.0, 필터 기준 0.5) |
| `bbox` | list[float] | [x1, y1, x2, y2] (픽셀 절대좌표) |

---

## 파일 위치 규칙 (MANDATORY)

```
Object_Detection/
├── src/          ← import 전용 라이브러리 (직접 실행 X)
│   ├── frame_extractor.py   ← 영상 → 프레임 추출
│   └── detector.py          ← YOLOv8 추론 래퍼
├── scripts/      ← 직접 실행 스크립트
│   └── batch_detect.py      ← 배치 사전 분석 (python scripts/batch_detect.py)
├── tests/        ← pytest
├── config/       ← 설정 yaml
│   └── detection_config.yaml
└── docs/
    ├── plans/    ← PLAN_0X 설계 문서
    └── reports/  ← 세션 리포트
```

| 파일 종류 | 저장 위치 |
|-----------|-----------|
| 프레임 추출 라이브러리 | `src/frame_extractor.py` |
| YOLOv8 추론 래퍼 | `src/detector.py` |
| 배치 실행 스크립트 | `scripts/batch_detect.py` |
| pytest | `tests/` |
| 모델/임계값/fps 설정 | `config/detection_config.yaml` |

**`Object_Detection/` 루트 또는 프로젝트 루트에 `.py` 파일 직접 생성 금지.**

---

## 기술 스택

```python
# 추론
from ultralytics import YOLO   # YOLOv8 (pip install ultralytics)

# 영상 처리
import cv2                     # 프레임 추출

# 데이터 처리
import pandas as pd            # parquet 저장
import numpy as np

# 기타
import os
from pathlib import Path
```

### 모델 선택 기준

| 모델 | 속도 | 정확도 | 권장 환경 |
|------|------|--------|----------|
| YOLOv8n | ⚡ 빠름 | 보통 | CPU / 테스트 |
| YOLOv8s | 중간 | 중간 | CPU (기본값) |
| YOLOv8x | 느림 | ⭐ 높음 | GPU |

> 기본값: `yolov8s.pt` (속도-정확도 균형). GPU 환경이면 `yolov8x.pt` 권장.
> 모델 파일은 `ultralytics`가 자동 다운로드하거나 `config/` 아래 명시적 경로 지정.

---

## 실행 환경

`myenv` (Python 3.12) 사용. 추가 패키지:

```bash
conda activate myenv
pip install ultralytics opencv-python-headless pandas
# GPU 환경: torch GPU 버전 별도 설치
# https://pytorch.org/get-started/locally/
```

---

## 실행

```bash
cd Object_Detection  # 또는 프로젝트 루트에서
python scripts/batch_detect.py --input-dir /path/to/videos --output data/vod_detected_object.parquet
python scripts/batch_detect.py --status   # 진행 상황 확인
python scripts/batch_detect.py --dry-run --limit 5  # 테스트

# ct_cl 필터 (기본값: TV 연예/오락)
python scripts/batch_detect.py --ct-cl "TV 연예/오락"  # 예능만 처리 (기본값)
python scripts/batch_detect.py --ct-cl ""              # 전체 처리
```

> ⚠️ **처리 대상**: `public.vod.ct_cl = 'TV 연예/오락'` (19,141건) 만 처리.
> 전체 처리 시 `--ct-cl ""`으로 필터 해제.

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` Object_Detection 섹션 참조 (Rule 1).
> 스키마 변경 시 Database_Design 기준으로 이 섹션도 업데이트할 것 (Rule 3).

### 업스트림 (읽기)

| 소스 | 컬럼/항목 | 타입 | 용도 |
|------|----------|------|------|
| 로컬 VOD 영상 파일 | `vod_id`, `file_path` | str | 추론 입력 |
| `public.vod` | `full_asset_id` | VARCHAR(64) | VOD 식별자 매핑 |
| `public.vod` | `youtube_video_id` | VARCHAR(20) | 트레일러 다운로드 |
| `public.vod` | `duration_sec` | REAL | 영상 길이 (초) |
| `public.vod` | `trailer_processed` | BOOLEAN | 미처리 VOD 필터 (FALSE/NULL) |

### 다운스트림 (쓰기)

| 대상 | 컬럼 | 타입 | 비고 |
|------|------|------|------|
| `data/vod_detected_object.parquet` (로컬) | `vod_id`, `frame_ts`, `label`, `confidence`, `bbox` | str/float/str/float/list | Shopping_Ad 소비 |
| `data/vod_clip_concept.parquet` (로컬) | `vod_id`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid` | str/float/str/float/str/bool | Shopping_Ad 소비 |
| `data/vod_stt_concept.parquet` (로컬) | `vod_id`, `start_ts`, `end_ts`, `transcript`, `keyword`, `ad_category`, `ad_hints` | str/float/float/str/str/str/list | Shopping_Ad 소비 |
| `public.detected_object_yolo` | `vod_id_fk`, `frame_ts`, `label`, `confidence`, `bbox` | VARCHAR(64)/REAL/VARCHAR(64)/REAL/REAL[] | YOLO bbox 탐지 (ON CONFLICT 미적용, write-once) |
| `public.detected_object_clip` | `vod_id_fk`, `frame_ts`, `concept`, `clip_score`, `ad_category`, `context_valid`, `context_reason` | VARCHAR(64)/REAL/VARCHAR(200)/REAL/VARCHAR(32)/BOOLEAN/TEXT | CLIP 개념 태깅 |
| `public.detected_object_stt` | `vod_id_fk`, `start_ts`, `end_ts`, `transcript`, `keyword`, `ad_category`, `ad_hints` | VARCHAR(64)/REAL/REAL/TEXT/VARCHAR(100)/VARCHAR(32)/TEXT | STT 키워드 추출 |
| `public.vod` | `trailer_processed` | BOOLEAN | 처리 완료 시 TRUE 갱신 |

---

## ⚠️ 알려진 이슈 / 현황

- DB 적재 스크립트 (`scripts/ingest_to_db.py`) 별도 구현 예정 — 스키마 확정 완료 (detected_object_yolo/clip/stt)
- 모델 파일 (.pt) git 커밋 금지 → `.gitignore`에 등록됨
- Phase 5 파인튜닝 진행 중 — TS.z01 완료 (train 20,872 / val 5,218), Drive 업로드 후 Colab 학습 예정
- Colab 로컬 디스크 ~80GB 한계 — TS.z02(107GB) 해제 시 Drive 직접 압축 해제 방식 사용 (`phase5_ts_drive_preprocess.ipynb`)

---

## TDD 개발 워크플로우

Object_Detection은 **Test Driven Development** 방식으로 개발한다.

### 사이클

```
1. Security Audit (Phase 시작 전)
   └── agents/SECURITY_AUDITOR.md 실행

2. PLAN 읽기
   └── docs/plans/PLAN_0X_*.md

3. Test Writer → 테스트 작성 (Red)
   └── agents/TEST_WRITER.md
   └── 출력: tests/test_phase{N}_*.py

4. Developer → 구현 (Green)
   └── agents/DEVELOPER.md
   └── 출력: src/frame_extractor.py, src/detector.py, scripts/batch_detect.py

5. Tester → 테스트 실행
   └── agents/TESTER.md
   └── FAIL 존재: Developer 재호출 (최대 3회)

6. Refactor → 코드 품질 개선 (Refactor)
   └── agents/REFACTOR.md

7. Reporter → 보고서 작성
   └── agents/REPORTER.md
   └── 출력: reports/phase{N}_report.md

8. Security Audit (커밋 직전)
   └── agents/SECURITY_AUDITOR.md

9. git commit / push / PR
```

### 에이전트 목록

| 파일 | 역할 |
|------|------|
| `agents/ORCHESTRATOR.md` | TDD 사이클 전체 관리 |
| `agents/TEST_WRITER.md` | 테스트 코드 작성 (Red) |
| `agents/DEVELOPER.md` | 구현 코드 작성 (Green) |
| `agents/TESTER.md` | pytest 실행 및 결과 수집 |
| `agents/REFACTOR.md` | 코드 품질 개선 (Refactor) |
| `agents/REPORTER.md` | 진행 보고서 생성 |
| `agents/SECURITY_AUDITOR.md` | 보안 점검 (커밋 전후) |

### 보고서 위치

```
Object_Detection/reports/
├── phase1_report.md    ← Phase 1 완료 후 생성
├── phase2_report.md    ← Phase 2 완료 후 생성
└── phase3_report.md    ← Phase 3 완료 후 생성
```

---

## 협업 규칙

- `main` 브랜치에 직접 Push 금지 — 반드시 Pull Request
- PR description 필수 항목:
  1. **변경사항 요약**: 추가/수정 파일
  2. **사후영향 평가**: `_agent_templates/IMPACT_ASSESSOR.md` 실행 결과
  3. **보안 점검 보고서**: `_agent_templates/SECURITY_AUDITOR.md` 실행 결과
