# Object_Detection — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.
> 최신 플로우 상세 → `docs/MATCHING_FLOW.md`

## 모듈 역할

**VOD 음식/관광지 2종 인식 + 지역명 추출** — 여행·먹방 VOD를 로컬에서 4종 멀티모달 분석하여
음식/관광지 카테고리 + 지역명을 추출한다. Shopping_Ad가 이 산출물을 소비한다.

> ⚠️ **로컬 전용 파이프라인**: VPC 인프라 제약으로 모든 연산은 로컬에서 수행.
> VPC에는 `detected_object_yolo/clip/stt` + `detected_object_ocr`(DDL 대기) 테이블에 적재.

### 광고 전략 (2026-03-19 확정)

| 인식 카테고리 | 광고 액션 | 예시 |
|-------------|----------|------|
| **관광지/지역** | 지자체 광고 팝업 (관광·축제) | "경주" 인식 → 경주 대릉원돌담길 축제 |
| **음식** | 제철장터 채널 상품 연계 (채널 이동/시청예약) | "삼겹살" 인식 → 제철장터 한우 상품 |

> **대상 VOD**: `genre_detail IN ('여행', '음식_먹방')`

### 데이터 플로우

```
VOD 영상 (로컬)
    → 프레임 추출 (1fps, frame_extractor.py)
    → YOLO v2 2단계 (COCO 필터 + best.pt 한식 71종, detector_v2.py)
    → CLIP zero-shot 장면 분류 (clip_scorer.py)
    → Whisper STT 키워드 추출 (stt_scorer.py + keyword_mapper.py)
    → OCR 자막 인식 (ocr_scorer.py + keyword_mapper.py)
    → 멀티시그널 스코어링 (10초 구간, 4종 교차검증)
    → parquet 4종 저장 (--save-parquet)
    → Shopping_Ad가 소비
```

### 산출물

| parquet | DB 테이블 | 내용 |
|---------|-----------|------|
| `vod_detected_object.parquet` | `detected_object_yolo` ✅ | YOLO food_detected |
| `vod_clip_concept.parquet` | `detected_object_clip` ✅ | CLIP 장면 분류 |
| `vod_stt_concept.parquet` | `detected_object_stt` ✅ | STT 키워드 639개 |
| `vod_ocr_concept.parquet` | `detected_object_ocr` (DDL 대기) | OCR 자막 텍스트 |

---

## 파일 위치 규칙 (MANDATORY)

```
Object_Detection/
├── src/              ← import 전용 라이브러리
│   ├── detector_v2.py        ← YOLO 2단계 (COCO + best.pt)
│   ├── clip_scorer.py        ← CLIP 장면 분류
│   ├── stt_scorer.py         ← Whisper STT
│   ├── ocr_scorer.py         ← EasyOCR 자막
│   ├── keyword_mapper.py     ← 키워드 매칭 (639개)
│   ├── frame_extractor.py    ← 프레임 추출
│   ├── audio_extractor.py    ← 오디오 추출
│   ├── context_filter.py     ← Brand Safety + 음식 필터
│   ├── location_tagger.py    ← 지역 태깅 (시뮬레이션)
│   └── vod_filter.py         ← DB ct_cl 필터
├── scripts/          ← 직접 실행 스크립트
│   ├── pilot_multimodal_test.py  ← 멀티모달 테스트 + parquet 생성
│   ├── batch_detect.py           ← YOLO 배치
│   ├── batch_clip_score.py       ← CLIP 배치
│   ├── batch_stt_score.py        ← STT 배치
│   ├── batch_ocr_score.py        ← OCR 배치
│   └── download_batch_target.py  ← 영상 다운로드
├── tests/            ← pytest
├── config/
│   ├── clip_queries_ko.yaml      ← CLIP 115개 쿼리
│   ├── stt_keywords.yaml         ← STT/OCR 639개 키워드
│   └── detection_config.yaml     ← YOLO 설정
├── models/           ← .pt 파일 (gitignore)
│   └── best.pt                   ← 한식 71종 파인튜닝 (57MB)
├── notebooks/        ← Colab 노트북
├── docs/
│   ├── MATCHING_FLOW.md          ← 파이프라인 플로우 (SSoT)
│   ├── BATCH_TARGET_20260320.md  ← 배치 대상 19건 목록
│   ├── plans/                    ← PLAN 설계 (완료)
│   └── reports/                  ← 리포트
└── _pilot_archive/   ← 레거시 (gitignore)
```

**`Object_Detection/` 루트에 `.py` 파일 직접 생성 금지.**

---

## 실행

```bash
# 멀티모달 테스트 + parquet 생성 (1회 실행으로 4종)
python scripts/pilot_multimodal_test.py --save-frames --save-parquet --videos data/batch_target/*.mp4

# 개별 배치
python scripts/batch_detect.py --input-dir data/batch_target --ct-cl ""
python scripts/batch_clip_score.py --input-dir data/batch_target --ct-cl ""
python scripts/batch_stt_score.py --input-dir data/batch_target --ct-cl ""
python scripts/batch_ocr_score.py --input-dir data/batch_target --ct-cl ""
```

---

## 인터페이스

> 컬럼/타입 상세 → `Database_Design/docs/DEPENDENCY_MAP.md` 참조 (Rule 1).

### 업스트림 (읽기)

| 소스 | 컬럼 | 타입 | 용도 |
|------|------|------|------|
| 로컬 VOD 영상 | file_path | str | 분석 입력 |
| `public.vod` | `full_asset_id`, `youtube_video_id`, `trailer_processed` | VARCHAR/VARCHAR(20)/BOOLEAN | VOD 식별 + 트레일러 |

### 다운스트림 (쓰기)

| 대상 | 주요 컬럼 | 비고 |
|------|----------|------|
| `detected_object_yolo` | vod_id_fk, frame_ts, label, confidence, bbox | ✅ DB 생성됨 |
| `detected_object_clip` | vod_id_fk, frame_ts, concept, clip_score, ad_category | ✅ DB 생성됨 |
| `detected_object_stt` | vod_id_fk, start_ts, end_ts, keyword, ad_category, ad_hints | ✅ DB 생성됨 |
| `detected_object_ocr` | vod_id_fk, frame_ts, detected_text, confidence, bbox | DDL 대기 |

---

## 현재 상태 (2026-03-22)

| 항목 | 상태 |
|------|------|
| 4종 멀티모달 파이프라인 | ✅ 완료 |
| best.pt 파인튜닝 (한식 71종) | ✅ 기본값 확정 |
| stt_keywords.yaml 639개 | ✅ 완료 |
| 관광지 컨텍스트 TRIGGER 규칙 | ✅ 완료 |
| 19건 배치 parquet 생성 | ✅ 완료 (739 TRIGGER) |
| DB 적재 | 🔲 조장 DDL 실행 + VOD 등록 후 |

---

## 협업 규칙

- `main` 직접 Push 금지 — PR 필수
- PR description: 변경사항 + 영향평가 + 보안점검
- `.pt`, `data/`, `.parquet` 커밋 금지 (gitignore)
