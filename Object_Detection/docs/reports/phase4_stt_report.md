# Phase 4 리포트 — Whisper STT 멀티모달 확장

- **브랜치**: Object_Detection
- **작성일**: 2026-03-15
- **선행 Phase**: Phase 3 (YOLO+CLIP 통합, context_filter 완료)
- **테스트 결과**: 12/12 PASS (누적 51/51 PASS)

---

## 목적

시각(YOLO+CLIP)만으로 구분 어려운 케이스를 **음성 대사**로 보완한다.

### 동기 예시

```
영상: 생선 먹는 장면
CLIP: "한식 밥상 식탁" (굴비인지 일반 생선인지 구분 불가)
오디오: "영광 굴비가 정말 맛있네요"
→ 굴비 광고 트리거 ← 정확도 대폭 향상
```

시각 신호만으로는 "굴비"와 "생선" 구분이 사실상 불가능하다.
STT로 발화된 제품명·지역명을 직접 추출하면 광고 타겟팅 정확도가 극적으로 올라간다.

---

## 아키텍처

```
VOD 영상 파일
    → 오디오 추출 (ffmpeg → 16kHz mono WAV, src/audio_extractor.py)
    → Whisper STT (로컬 small 모델, src/stt_scorer.py)
      → segments: [{start, end, text}, ...]
    → 키워드 매핑 (config/stt_keywords.yaml, src/keyword_mapper.py)
      → 매칭된 키워드 → ad_category + ad_hints
    → vod_stt_concept.parquet 저장
```

CLIP 파이프라인(`vod_clip_concept.parquet`)과 독립적으로 동작.
Shopping_Ad가 `vod_id + 시간 구간` 기준으로 두 파일을 조인하여 최종 광고를 결정한다.

---

## 구현 파일

| 파일 | 역할 |
|------|------|
| `src/audio_extractor.py` | ffmpeg subprocess → 16kHz mono WAV 추출 |
| `src/stt_scorer.py` | openai-whisper small 모델 래퍼, segments 반환 |
| `src/keyword_mapper.py` | transcript 키워드 매칭 → ad_category + ad_hints |
| `scripts/batch_stt_score.py` | 배치 실행, 상태 파일, parquet 저장 |
| `config/stt_keywords.yaml` | 키워드 → ad_category + 복수 지역 ad_hints 매핑 |
| `tests/test_phase4_stt.py` | TDD Red → Green (12개 테스트) |

---

## 산출물 스키마 (`vod_stt_concept.parquet`)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `start_ts` | float | 발화 시작 (초) |
| `end_ts` | float | 발화 종료 (초) |
| `transcript` | str | 해당 구간 발화 텍스트 |
| `keyword` | str | 매칭된 키워드 (e.g. "대게") |
| `ad_category` | str | 광고 카테고리 (e.g. "지방특산물") |
| `ad_hints` | str | 지역 광고 힌트 (e.g. "영덕 대게 직송") |
| `context_valid` | bool | 항상 True (키워드 매칭 = 컨텍스트 확인) |
| `context_reason` | str | "keyword_match" |

---

## 키워드 설계 철학

### 1. 키워드 → 복수 지역 ad_hints

지역 특산물은 단일 지역에 고정하지 않는다.
하나의 키워드가 여러 지역에 매핑되며, Shopping_Ad가 **사용자 위치** 기반으로 최적 ad_hint를 선택한다.

```yaml
지방특산물:
  대게:
    ad_hints:
      - "영덕 대게 직송"
      - "울진 대게 특가"
  녹차:
    ad_hints:
      - "보성 녹차 특가"
      - "하동 녹차 직송"
      - "제주 녹차"
```

→ Object_Detection: "무엇" 탐지
→ Shopping_Ad: "어떤 지역 상품" 결정 (사용자 위치 기반)

### 2. 카테고리 구성

| 카테고리 | 키워드 예시 |
|----------|------------|
| 지방특산물 | 대게, 굴비, 녹차, 사과, 복숭아 |
| 건강식품 | 홍삼, 콜라겐, 유산균, 오메가3 |
| 주방가전 | 에어프라이어, 밥솥, 블렌더, 커피머신 |
| 여행상품 | 제주도, 강원도, 해외여행, 크루즈 |

---

## TDD 테스트 결과

| ID | 테스트명 | 결과 |
|----|---------|------|
| P4-01 | stt_keywords.yaml 필수 카테고리 포함 | ✅ PASS |
| P4-02 | 모든 키워드에 ad_hints 존재 | ✅ PASS |
| P4-03 | 모든 키워드가 string 타입 | ✅ PASS |
| P4-04 | KeywordMapper import 성공 | ✅ PASS |
| P4-05 | 키워드 매칭 시 레코드 반환 | ✅ PASS |
| P4-06 | 키워드 미매칭 시 빈 리스트 반환 | ✅ PASS |
| P4-07 | SttScorer import 성공 | ✅ PASS |
| P4-08 | SttScorer 초기화 (whisper 있을 때) | ✅ PASS |
| P4-09 | transcribe() 세그먼트 반환 (ffmpeg 필요) | ✅ PASS |
| P4-10 | AudioExtractor import 성공 | ✅ PASS |
| P4-11 | ffmpeg 설치 확인 | ✅ PASS |
| P4-12 | 레코드 스키마 검증 | ✅ PASS |

**12/12 PASS** | 누적 전체 **51/51 PASS**

---

## 한계 및 향후 과제

| 한계 | 내용 |
|------|------|
| 파일럿 미실행 | 실제 VOD에 대한 STT 결과 검증 미완료 |
| 키워드 recall | 방언, 줄임말, 발음 오류 → 매칭 실패 가능 |
| Whisper 처리 속도 | small 모델 기준 1분 영상 → 약 30~60초 (CPU) |
| 키워드 목록 | 현재 시드 키워드 수준 — 실운영 전 대폭 확장 필요 |

### 권장 후속 작업

1. **파일럿 실행**: `batch_stt_score.py --limit 10 --random` 으로 10건 실제 STT 검증
2. **키워드 확장**: 카테고리별 50개 이상으로 `stt_keywords.yaml` 확충
3. **CLIP+STT 융합 점수**: 두 파이프라인 score를 가중 합산하는 융합 레이어 설계
4. **Shopping_Ad 연동**: `vod_stt_concept.parquet` 소비 로직 구현

---

## Phase 1~4 누적 현황

| Phase | 내용 | 테스트 | 상태 |
|-------|------|--------|------|
| Phase 1 | YOLOv11 배치 사물인식 | 13/13 | ✅ |
| Phase 2 | CLIP zero-shot 개념 태깅 | 13/13 (누적 26/26) | ✅ |
| Phase 3 | YOLO+CLIP 통합 + context_filter | 13/13 (누적 39/39) | ✅ |
| Phase 3b | context_filter 강화 (negative 확장) | — | ✅ |
| Phase 4 | Whisper STT 멀티모달 확장 | 12/12 (누적 51/51) | ✅ |
