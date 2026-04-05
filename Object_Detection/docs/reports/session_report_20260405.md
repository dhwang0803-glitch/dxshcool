# 세션 리포트 — 2026-04-05

## 작업 요약

### 골목식당 156회 추가 배치 (20번째 VOD)

- **VOD**: 백종원의 골목식당 156회 (추어탕 에피소드)
- **DB**: `cjc|M4862144LSGL00455001` (등록 확인)
- **file_id**: `food_golmok_156`
- **YouTube**: `sg0bGGSok_s`
- **영상**: `data/batch_target/food_golmok_156.mp4` (26.6MB, 720p)

### 4종 멀티모달 분석 결과

| 모델 | 건수 | 주요 결과 |
|------|------|----------|
| YOLO | 19건 | food_detected (conf 0.50~0.96), 주요 구간 01:59~02:03 |
| CLIP | 25건 | 한국 전통 반찬 밥상 (0.31), 해산물 한국 요리 (0.30) |
| STT | 9건 | 추어탕(4), 만두(2), 김치(1), 들깨(2) |
| OCR | 63건 | 추어탕, 골목식당, 등촌동 등 자막 |

### TRIGGER 구간

| 구간 | score | 신호 |
|------|-------|------|
| 02:00~02:10 | 8 (3종) | YOLO + STT(김치) + CLIP |
| 02:10~02:20 | 7 (3종) | STT(김치) + CLIP + OCR(김치) |
| 02:20~02:30 | 5 (2종) | YOLO + CLIP |
| 02:50~03:00 | 6 (2종) | YOLO + STT(들깨) |

### Shopping_Ad 매칭
- **남원추어탕** 매칭 성공 (제철장터 4/5 05:55~06:55)
- Top 1 키워드 "추어탕" → 직접 매칭
- ts_start: 150초 (2:30, 추어탕 클로즈업 기준 수동 보정)

---

## 변경 파일

| 파일 | 변경 |
|------|------|
| `data/batch_target/food_golmok_156.mp4` | 영상 다운로드 |
| `data/batch_target/vod_metadata.json` | food_golmok_156 엔트리 추가 |
| `data/parquet_output/vod_detected_object.parquet` | YOLO 19건 추가 |
| `data/parquet_output/vod_clip_concept.parquet` | CLIP 25건 추가 |
| `data/parquet_output/vod_stt_concept.parquet` | STT 9건 추가 |
| `data/parquet_output/vod_ocr_concept.parquet` | OCR 63건 추가 |

> 모두 gitignore 대상 (data/)

---

## 배치 현황

- 기존 19건 → **20건** (골목식당 156 추가)
- 전체 TRIGGER: 739건 → 753건 (+14건)
