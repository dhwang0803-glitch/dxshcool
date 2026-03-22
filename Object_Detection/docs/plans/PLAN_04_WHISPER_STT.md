> ✅ **완료** (Phase 4). STT 키워드 현재 599개. 최신 → `docs/MATCHING_FLOW.md`

# PLAN_04 — Whisper STT 멀티모달 확장

- **브랜치**: Object_Detection
- **Phase**: Phase 4
- **작성일**: 2026-03-15
- **선행 조건**: Phase 3 완료 (CLIP + YOLO 통합)

---

## 목적

시각(YOLO+CLIP)만으로 구분 어려운 케이스를 **음성 대사**로 보완한다.

```
영상: 생선 먹는 장면
CLIP: "한식 밥상 식탁" (굴비인지 일반 생선인지 구분 불가)
오디오: "영광 굴비가 정말 맛있네요"
→ 굴비 광고 트리거 ← 정확도 대폭 향상
```

---

## 아키텍처

```
VOD 영상 파일
    → 오디오 추출 (ffmpeg, src/audio_extractor.py)
    → Whisper STT (로컬, src/stt_scorer.py)
    → 키워드 매핑 (config/stt_keywords.yaml, src/keyword_mapper.py)
    → vod_stt_concept.parquet 저장
```

**CLIP 파이프라인과 독립** — 별도 parquet 출력.
Shopping_Ad가 `vod_id + 시간 구간` 기준으로 두 파일 조인.

---

## 구현 파일

| 파일 | 역할 |
|------|------|
| `src/audio_extractor.py` | VOD 영상 → 오디오 추출 (ffmpeg subprocess) |
| `src/stt_scorer.py` | Whisper 모델 래퍼 → transcript + 구간 타임스탬프 |
| `src/keyword_mapper.py` | transcript 키워드 매칭 → ad_category + ad_hints |
| `scripts/batch_stt_score.py` | 배치 실행 스크립트 |
| `config/stt_keywords.yaml` | 키워드 → ad_category 매핑 테이블 |

---

## 산출물 스키마 (`vod_stt_concept.parquet`)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| `vod_id` | str | VOD 식별자 |
| `start_ts` | float | 발화 구간 시작 (초) |
| `end_ts` | float | 발화 구간 종료 (초) |
| `transcript` | str | 해당 구간 인식된 텍스트 |
| `keyword` | str | 매칭된 키워드 |
| `ad_category` | str | 카테고리 (지방특산물/한식 등) |
| `ad_hints` | str | 광고 힌트 (예: "영광 굴비 특가") |
| `region` | str | 시뮬레이션 지역 |
| `sim_lat` | float | 시뮬레이션 위도 |
| `sim_lng` | float | 시뮬레이션 경도 |
| `context_valid` | bool | 광고 트리거 적합 여부 |
| `context_reason` | str | 판단 근거 |

---

## `config/stt_keywords.yaml` 구조

```yaml
# 키워드 → ad_category + ad_hints 매핑
# 복수 지역 매핑 지원 (concept → region 연결 설계 반영)

지방특산물:
  굴비:
    ad_hints: ["영광 굴비 특가", "영광 굴비 선물세트"]
  조기:
    ad_hints: ["영광 굴비 특가"]
  대게:
    ad_hints: ["영덕 대게 직송", "울진 대게 특가"]
  전복:
    ad_hints: ["완도 전복 산지직송"]
  장어:
    ad_hints: ["고창 풍천장어", "통영 장어"]
  한우:
    ad_hints: ["횡성 한우 직송"]
  흑돼지:
    ad_hints: ["제주 흑돼지 특가"]

한식:
  김치:
    ad_hints: ["전라도 김치", "갓김치 선물세트"]
  된장:
    ad_hints: ["전통 된장 특가"]
  젓갈:
    ad_hints: ["강경 젓갈 직송"]

과일채소:
  사과:
    ad_hints: ["예산 사과 직송", "청송 사과 특가", "영주 사과"]
  감귤:
    ad_hints: ["제주 감귤 산지직송"]
  복숭아:
    ad_hints: ["영동 복숭아 특가"]
  녹차:
    ad_hints: ["보성 녹차", "하동 녹차", "제주 녹차"]
  쌀:
    ad_hints: ["이천쌀 직송", "철원 오대쌀"]

여행지:
  제주:
    ad_hints: ["제주도 여행 패키지"]
  강릉:
    ad_hints: ["강릉 여행 특가"]
  부산:
    ad_hints: ["부산 해운대 여행"]
```

---

## keyword_mapper 설계

```python
# 복수 ad_hints 중 하나 랜덤 선택 (A/B 실험 가능)
# 추후 사용자 위치 기반으로 최적 힌트 선택 (Shopping_Ad 역할)
```

**매칭 방식**: 대화 텍스트에 키워드 포함 여부 (`in` 연산).
**복수 키워드 매칭**: 한 구간에 여러 키워드 → 복수 레코드 생성.

---

## 오디오 추출 설계

```python
# ffmpeg subprocess 방식 (별도 설치 필요)
# 출력: 16kHz mono WAV (Whisper 권장 포맷)
subprocess.run([
    "ffmpeg", "-i", video_path,
    "-ar", "16000", "-ac", "1", "-f", "wav",
    audio_path
])
```

---

## Whisper 모델 선택

| 모델 | 속도 | 정확도 | 권장 환경 |
|------|------|--------|----------|
| `tiny` | ⚡ 빠름 | 낮음 | 테스트 |
| `base` | 빠름 | 보통 | CPU 기본값 |
| `small` | 중간 | **좋음** | CPU 권장 ← **채택** |
| `medium` | 느림 | 높음 | GPU |

- 기본값: `small` (한국어 인식률 실용적, CPU 동작)
- `--model` 옵션으로 교체 가능

---

## context_valid 판단 (STT)

CLIP보다 단순 — 키워드가 발화에 나오면 기본 `True`.
차단 조건:

| 조건 | context_valid | 이유 |
|------|--------------|------|
| 키워드 매칭 정상 발화 | True | `keyword_match` |
| 키워드 점수 < 임계값 (Whisper no_speech_prob 높음) | False | `low_confidence` |

---

## Shopping_Ad 조인 방식

```
vod_clip_concept.parquet  → frame_ts 기준 CLIP 태그
vod_stt_concept.parquet   → start_ts ~ end_ts 구간 기준 STT 태그

조인: vod_id 동일 + frame_ts가 [start_ts, end_ts] 범위 내
→ 두 신호 중 하나라도 context_valid=True면 광고 트리거 후보
```

---

## 완료 기준

### 코드 구현

- [ ] `src/audio_extractor.py` — ffmpeg 오디오 추출
- [ ] `src/stt_scorer.py` — Whisper 래퍼 (transcript + 타임스탬프)
- [ ] `src/keyword_mapper.py` — 키워드 매핑 + context_valid
- [ ] `scripts/batch_stt_score.py` — 배치 실행 + 상태 파일 + parquet 저장
- [ ] `config/stt_keywords.yaml` — 키워드 매핑 테이블

### 테스트

- [ ] Phase 4 pytest 작성 및 PASS

### 문서

- [ ] `docs/reports/phase4_stt_report.md` 작성

---

## 의존성

```bash
pip install openai-whisper
# ffmpeg 별도 설치 필요 (시스템 패키지)
# Windows: winget install ffmpeg  또는 chocolatey
```
