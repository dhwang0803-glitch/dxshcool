# Phase 5 세션 리포트 — YOLOv11 파인튜닝 준비

- **브랜치**: Object_Detection
- **작성일**: 2026-03-16
- **선행 Phase**: Phase 4 완료 (51/51 PASS), PR #31 MERGED
- **세션 목표**: Colab 파인튜닝 노트북 구현 + AI Hub 데이터 다운로드 환경 설정

---

## 배경

Phase 1 파일럿에서 YOLO11s(COCO 80종)는 한식(비빔밥, 김치찌개, 굴비, 대게 등) 탐지 0건.
Phase 2~4에서 CLIP + Whisper STT로 우회 구현을 완료했으나,
조장(황대원) 제안에 따라 Phase 5에서 YOLO 파인튜닝을 통한 정공법 해결을 시도한다.

---

## 세션 작업 내역

### 1. 설계 문서 작성

| 문서 | 위치 | 내용 |
|------|------|------|
| PLAN_05 | `docs/plans/PLAN_05_YOLO_FINETUNE.md` | 5단계 파인튜닝 플랜 |
| 비교 리포트 | `docs/reports/phase5_yolo_finetune_plan.md` | 파인튜닝 vs CLIP+STT 트레이드오프 분석 |

**결론**: 두 방식은 경쟁이 아닌 보완 관계. 파인튜닝 완료 후 CLIP·STT 파이프라인은 수정 없이 유지.

### 2. Colab 파인튜닝 노트북 구현

**파일**: `notebooks/phase5_finetune_colab.ipynb`

| Step | 내용 |
|------|------|
| Step 0 | GPU 확인 + Drive 마운트 |
| Step 0.5 | aihubshell 설치 + 인증 + 데이터 다운로드 |
| Step 1 | `collect_all_classes()` — JSON `food_type.fc` 전체 스캔, 800종 동적 수집 |
| Step 2 | `build_full_dataset()` — JSON → YOLO 포맷 변환 (bbox 오류/이미지 누락만 skip) |
| Step 3 | `data.yaml` 동적 생성 (nc=800) |
| Step 4 | `model.train(yolo11s.pt, epochs=100, batch=16, patience=20, save_period=10)` |
| Step 5 | 검증 (mAP@0.5 목표 ≥ 0.60) |
| Step 6 | A/B 비교 (기존 yolo11s.pt vs 파인튜닝 best.pt) |
| Step 7 | best.pt 로컬 적용 가이드 |

**핵심 설계 결정**:
- 클래스 필터링 없음 — 800종 전체 학습 (초기 TARGET_CLASSES 21종 필터에서 변경)
- `LOCAL_TMP=/content/aihub_tmp` — aihubshell의 경로 공백 버그 우회
- Drive 경로: `/content/drive/MyDrive/LGHellovision/Project 02/Object Detection`

### 3. 좌표 변환 로직

AI Hub JSON(절댓값 좌상단 기준) → YOLO(정규화 중심점 기준):

```python
cx = (x + bw/2) / img_w
cy = (y + bh/2) / img_h
nw = bw / img_w
nh = bh / img_h
```

---

## aihubshell 이슈 및 해결

### 발생한 문제들

| 문제 | 원인 | 해결 |
|------|------|------|
| REST API 404 | AI Hub는 REST 직접 호출 불가 | aihubshell 전용 툴 사용으로 전환 |
| aihubshell 다운로드 502 "인증실패" | API 키 권한 문제 | API 키 재발급 시도 |
| `-aihubid`/`-aihubpw` 미지원 | aihubshell v0.6 API 키 방식만 지원 | — |
| **해외 IP 차단 (근본 원인)** | Google Colab 서버(미국)에서 다운로드 원천 차단 | 로컬 INNORIX 다운로드 + Drive 수동 업로드 |

### 최종 확인된 제약

```
AI Hub aihubshell — 해외 서버(Colab 포함)에서 -mode d(다운로드) 완전 차단
- -mode l (목록 조회): API 키로 정상 동작 ✅
- -mode d (다운로드): "AI Hub는 해외에서의 데이터 다운로드를 제한" ❌
```

`-mode l`은 성공하여 파일 트리 조회 가능 → 인증 자체는 정상.
다운로드만 국내 IP 제한.

### 해결책: 로컬 INNORIX + Drive 수동 업로드

```
로컬 PC(한국)
  → INNORIX로 TL.zip(142MB) + VL.zip(18MB) 다운로드
  → Google Drive > LGHellovision > Project 02 > Object Detection > aihub_food 업로드
  → Colab cell-8 (zipfile 압축 해제)로 처리
```

cell-8을 aihubshell 다운로드 방식에서 **zipfile 압축 해제 방식**으로 교체 완료.

---

## 현재 상태

| 항목 | 상태 |
|------|------|
| PLAN_05 설계 문서 | ✅ 완료 |
| Colab 노트북 구현 | ✅ 완료 (커밋 bfca640) |
| TL.zip + VL.zip 로컬 다운로드 | ✅ 완료 (로컬 Downloads/aihub) |
| TL.zip + VL.zip Drive 업로드 | 🔲 진행 예정 |
| cell-8 실행 (압축 해제) | 🔲 업로드 후 진행 |
| 학습 이미지 (TS.z01~, 840GB) | 🔲 미해결 — 로컬 aihubshell 후 Drive 업로드 필요 |
| Step 4 학습 실행 | 🔲 이미지 준비 후 진행 |

---

## 데이터셋 정보

**AI Hub '비전영역, 음식이미지 및 정보소개 텍스트 데이터'** (dataSetSn=71564)

| 파일 | 크기 | 용도 | 상태 |
|------|------|------|------|
| TL.zip (key=502339) | 142 MB | 학습 라벨 JSON | ✅ 로컬 완료 |
| VL.zip (key=502341) | 18 MB | 검증 라벨 JSON | ✅ 로컬 완료 |
| TS.z01~TS.z07 (key=502331~502337) | 각 100 GB | 학습 이미지 분할 | 🔲 미다운로드 |
| TS.zip (key=502338) | 40 GB | 학습 이미지 마지막 | 🔲 미다운로드 |
| VS.zip (key=502340) | 89 GB | 검증 이미지 | 🔲 불필요 (학습 데이터 80:20 분리 대체) |

- 총 232,087장 / 800종
- 4대 분류: 특수외식 35% / 일반외식배달 34.7% / 끼니대체 26.4% / 음료차류 3.9%

---

## 학습 이미지 확보 방안 (미해결)

**문제**: 840GB를 Colab에 올리는 것은 물리적 한계.

**권장 방안**:

| 방안 | 설명 | 현실성 |
|------|------|--------|
| 로컬 aihubshell + Drive 업로드 | 로컬에서 TS.z01 1개(100GB) 받아 Drive 업로드 | △ (업로드 시간 수 시간) |
| 1개 split만 사용 | TS.z01 1개 ≈ 29,000장 → 충분한 파인튜닝 가능 | ✅ 권장 |
| 전체 840GB | 비현실적 (Drive 용량 + 업로드 시간) | ❌ |

→ **다음 세션 과제**: 로컬 aihubshell로 TS.z01(100GB)만 받아서 Drive에 업로드 후 학습 시작.

---

## 노트북 커밋 이력

| 커밋 | 내용 |
|------|------|
| `d9d2234` | 전면 재작성 (save_dir→dest_dir 통일, LOCAL_TMP 도입, 800종 전체 스캔) |
| `b887917` | aihubshell 인증 — API키+ID/PW 이중 지원 |
| `6ea016f` | 테스트 셀 오탐 수정 (returncode→파일키 존재 여부로 판정 변경) |
| `bfca640` | cell-8 zipfile 압축 해제 방식으로 교체 (해외 IP 차단 대응) |

---

## 기대 효과 (학습 완료 후)

| 항목 | Phase 4 현재 | Phase 5 이후 |
|------|------------|------------|
| 한식 탐지 | CLIP 우회 (프레임 전체 유사도) | YOLO bbox 직접 탐지 |
| 굴비·대게 구분 | STT 의존 (recall 낮음) | 시각 탐지 + STT 이중 확인 |
| context_filter 정확도 | CLIP negative 차단 위주 | YOLO 한식 bbox + 식기류 동반 확인 강화 |
| Shopping_Ad 연동 | concept 기반 매칭 | bbox 좌표 기반 정밀 매핑 가능 |

---

## 구현 접근 방식 재검토 (2026-03-16 오후)

조장(황대원) 추가 제안: *"Ollama 로컬 설치했으니 YOLO 보조로 활용하면 어떨까?"*

### 4가지 방식 비교

| 항목 | A. 현재 CLIP | B. Ollama→쿼리 생성 | C. Ollama→직접 분석 | D. YOLO 파인튜닝 |
|------|------------|-------------------|-------------------|----------------|
| 속도 | ⚡ 빠름 | ⚡ 빠름 | 🐢 느림 | ⚡ 빠름 |
| 구현 난이도 | ✅ 완료 | 쉬움 | 중간 | 높음 |
| 한식 커버리지 | 낮음 | **높음 (800종+)** | 높음 | **높음 (bbox)** |
| 학습 데이터 | 불필요 | 불필요 | 불필요 | 840GB |
| bbox 좌표 | ❌ | ❌ | ❌ | ✅ |

### CLIP은 학습 불필요

CLIP은 OpenAI가 4억 장으로 사전학습 완료된 zero-shot 모델.
`clip_queries.yaml`에 텍스트만 추가하면 즉시 인식 — 별도 학습/데이터셋 불필요.

### 구현 우선순위

```
1순위: B — Ollama로 clip_queries.yaml 800종 자동 생성 (즉시 가능)
2순위: D — YOLO 파인튜닝 (이미지 데이터 확보 후 B 위에 추가)
보류:  C — 프레임마다 LLM 호출로 배치 처리 속도 부적합
```

상세: `docs/plans/PLAN_05_YOLO_FINETUNE.md` — 구현 접근 방식 비교 섹션

---

## 다음 액션

### 단기 (즉시)
1. **TL.zip + VL.zip → Google Drive 업로드** 완료 → Colab cell-8 실행
2. **Colab Step 1** 실행 → JSON 파싱 + 800종 클래스 목록 확인
3. **방식 B 구현**: Ollama로 `clip_queries.yaml` 800종 확장 → 기존 CLIP 파이프라인에 즉시 적용

### 중기 (이미지 확보 후)
4. **로컬 aihubshell로 TS.z01(100GB) 다운로드** → Drive 업로드 → Colab Step 2~4 학습
5. **방식 D 완성**: best.pt → `models/korean_food_v1_best.pt` → `config/detection_config.yaml` 경로 교체
6. **A/B 비교**: 기존 yolo11s.pt vs 파인튜닝 best.pt + 확장된 CLIP 쿼리 3중 비교
