# Gen_Sentence — 추천 문구 생성 파이프라인 기획

## 브랜치

`gen_sentence`

## 목적

추천 엔진(CF_Engine, Vector_Search)이 산출한 추천 결과에 대해
**왜 추천되었는지(reason)** 와 **감성 카피(copy)** 를 LLM으로 생성하여
UI 추천 카드에 표시한다.

---

## 생성 대상

| 필드 | 성격 | 예시 |
|------|------|------|
| `recommendation_reason` | 사실 기반 설명 | "봉준호 감독의 작품을 3편이나 시청하셨네요" |
| `recommendation_copy` | 감성 카피 (클릭 유도) | "아카데미를 뒤흔든 봉준호 감독의 걸작, 아직 안 보셨다면 지금 꼭." |
| `tags` | 핵심 키워드 태그 | `["봉준호", "아카데미", "스릴러"]` |

---

## 왜 파인튜닝인가

| 관점 | RAG + 프롬프트 | 파인튜닝 |
|------|---------------|---------|
| 톤/스타일 일관성 | 매번 프롬프트로 지시 → 흔들림 | 학습된 톤 고정 |
| 출력 포맷 | JSON 구조 실패 가능 | 안정적 |
| 추론 비용 | 긴 프롬프트 = 높은 토큰 | 짧은 프롬프트로 동작 |
| 로컬 실행 | 대형 모델 필요 → 무거움 | 소형 모델 + LoRA → 가벼움 |
| 한국어 VOD 도메인 | 일반 지식에 의존 | 도메인 특화 |

**결론**: 프로덕션 수준의 톤 일관성 + 로컬 소형 모델 실행이 목표이므로 파인튜닝이 적합.

---

## 추천 사유 유형 분류

학습 데이터 구축 시 아래 유형별로 Seed를 작성한다.

| 유형 | 추천 시그널 | reason 예시 | copy 예시 |
|------|-----------|-------------|----------|
| 감독 팬 | 같은 감독 3편+ 시청 | "봉준호 감독 작품을 즐겨 보셨습니다" | "칸의 황금종려상, 그 시선이 향하는 곳" |
| 출연진 팬 | 같은 배우 출연작 반복 | "블랙핑크 멤버들의 출연작" | "무대 밖에서 더 빛나는 그들의 예능 매력" |
| 분위기 유사 | 임베딩 유사도 높음 | "시청하신 '리틀 포레스트'와 비슷한 분위기" | "화창한 여름날, 풀냄새가 나는 영화" |
| 장르 선호 | 장르 시청 비율 높음 | "스릴러 장르를 자주 시청하셨습니다" | "손에 땀을 쥐게 하는 반전의 연속" |
| 인기 급상승 | TRENDING 스코어 | "이번 주 급상승 콘텐츠" | "지금 모두가 이야기하는 바로 그 작품" |
| 시리즈 후속 | 같은 시리즈 시청 | "시청하신 시즌 1의 다음 이야기" | "기다렸던 그 이야기, 드디어 계속됩니다" |
| 연령대 인기 | 같은 연령대 선호 | "같은 연령대에서 가장 인기 있는 작품" | "당신과 같은 세대가 사랑하는 이야기" |
| 제작사/프랜차이즈 | 같은 제작사 선호 | "즐겨 보신 마블 시리즈의 최신작" | "히어로 유니버스, 그 다음 챕터" |

---

## 튜닝 전략

### 베이스 모델 후보

| 모델 | 파라미터 | 한국어 | VRAM 요구 (QLoRA) | Ollama 지원 |
|------|---------|--------|-------------------|------------|
| Gemma 2 9B | 9B | 양호 | ~8GB | O |
| Llama 3.1 8B | 8B | 보통 | ~8GB | O |
| EXAONE 3.0 7.8B | 7.8B | 우수 (LG AI) | ~8GB | O |
| Qwen 2.5 7B | 7B | 우수 | ~6GB | O |

**선정 기준**: 한국어 성능 > Ollama 호환 > VRAM 효율.
Phase 0에서 zero-shot 비교 후 확정.

### 튜닝 방식

**QLoRA** (Quantized Low-Rank Adaptation)

- 4-bit 양자화 + LoRA rank 16~32
- 학습 환경: Google Colab (T4/A100)
- 프레임워크: `transformers` + `peft` + `trl` (SFTTrainer)
- 출력: LoRA adapter 파일 (~50MB) → Ollama Modelfile로 통합

### 학습 데이터 포맷 (Instruction Tuning)

```json
{
  "instruction": "추천 사유와 VOD 정보를 바탕으로 추천 문구를 생성하세요.",
  "input": {
    "recommendation_type": "COLLABORATIVE",
    "reason_signal": "감독 팬 — 봉준호 감독 작품 3편 시청 (기생충, 마더, 옥자)",
    "vod_metadata": {
      "asset_nm": "살인의 추억",
      "director": "봉준호",
      "genre": "스릴러",
      "cast_lead": "송강호, 김상경",
      "smry": "1986년 경기도 화성에서 연쇄 살인 사건이 발생하고...",
      "release_date": "2003-05-02"
    },
    "user_context": {
      "watched_same_director": ["기생충", "마더", "옥자"],
      "preferred_genres": ["스릴러", "드라마"],
      "recent_watch_pattern": "주말 저녁 영화 집중"
    }
  },
  "output": {
    "recommendation_reason": "봉준호 감독의 작품을 3편이나 시청하셨네요",
    "recommendation_copy": "송강호와 봉준호, 전설의 시작점. 아직 안 보셨다면 지금 꼭.",
    "tags": ["봉준호", "송강호", "스릴러"]
  }
}
```

---

## 학습 데이터 구축 (3단계)

전체 작업의 **70%** 가 여기에 집중된다.

### Step 1: Seed 데이터 수작업 (50~100건)

- 추천 사유 유형별 10건씩 직접 작성
- 톤/스타일의 기준점 (Gold Standard)
- DB에서 실제 VOD 메타데이터를 조회하여 사실 기반으로 작성

### Step 2: LLM 증강 (500~1,000건)

- GPT-4 또는 Claude에 Seed 데이터를 few-shot 예시로 제공
- DB에서 실제 VOD 메타 + 가상 시청 이력 조합으로 대량 생성
- 사람이 검수: 톤 불일치, 사실 오류, 포맷 이탈 제거

### Step 3: 반복 개선

- 튜닝된 모델 출력을 사람이 평가 (1~5점)
- 나쁜 케이스를 수정하여 재학습 데이터에 추가
- 2~3회 반복으로 품질 수렴

---

## 시스템 아키텍처

```
[추천 엔진 출력]
  CF_Engine / Vector_Search
  → serving.vod_recommendation
  → serving.popular_recommendation
        │
        ▼
[컨텍스트 조립] context_builder.py
  1) 추천 사유 분석:
     - COLLABORATIVE → 시청 이력에서 공통 패턴 추출 (감독/배우/장르)
     - VISUAL_SIMILARITY → 유사 VOD 메타 비교
     - CONTENT_BASED → source_vod 메타 비교
     - POPULAR/TRENDING → 인기/급상승 시그널
  2) VOD 메타데이터 조회 (public.vod)
  3) 유저 시청 이력 집계 (public.watch_history)
  4) JSON 컨텍스트 조립
        │
        ▼
[튜닝된 LLM] copy_generator.py
  Ollama 로컬 실행 (LoRA adapter + 베이스 모델)
  → reason + copy + tags 생성
        │
        ▼
[품질 필터] quality_filter.py
  - JSON 파싱 성공 여부
  - reason/copy 길이 제약 (10~100자)
  - 금칙어 필터
  - 사실 검증 (감독명/배우명이 메타와 일치하는지)
        │
        ▼
[DB 적재]
  serving.recommendation_copy 테이블
  (vod_recommendation과 1:1 또는 1:N 관계)
        │
        ▼
[API_Server → Frontend]
  추천 카드에 reason + copy 표시
```

---

## 폴더 구조

```
gen_sentence/
├── src/
│   ├── context_builder.py      ← 추천 시그널 + VOD 메타 + 시청 이력 조립
│   ├── copy_generator.py       ← Ollama 호출 래퍼 (프롬프트 구성 + JSON 파싱)
│   └── quality_filter.py       ← 생성 결과 검증 (포맷/길이/사실 확인)
├── scripts/
│   ├── build_seed_data.py      ← DB에서 VOD 메타 추출 → Seed 템플릿 생성
│   ├── augment_training_data.py ← LLM으로 학습 데이터 증강
│   ├── train_lora.py           ← QLoRA 학습 (Colab용 노트북 겸용)
│   ├── evaluate_model.py       ← 튜닝 전후 품질 비교
│   └── batch_generate.py       ← 배치 문구 생성 → DB 적재
├── data/
│   ├── seed_examples.jsonl     ← 수작업 Seed 50~100건
│   ├── training_data.jsonl     ← 증강 완료 학습 데이터
│   └── eval_results.jsonl      ← 평가 결과
├── config/
│   ├── generation_config.yaml  ← 모델, 프롬프트 템플릿, 길이 제약
│   └── .env.example            ← DB 접속 정보 템플릿
├── tests/
│   ├── test_context_builder.py
│   ├── test_copy_generator.py
│   └── test_quality_filter.py
└── docs/
    └── plans/                  ← Phase별 PLAN 문서
```

---

## DB 스키마 (Database_Design 협의 필요)

### 옵션 A: 별도 테이블 `serving.recommendation_copy`

```sql
CREATE TABLE serving.recommendation_copy (
    copy_id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recommendation_id   BIGINT NOT NULL,         -- FK → serving.vod_recommendation
    recommendation_reason TEXT NOT NULL,          -- 사실 기반 설명
    recommendation_copy TEXT NOT NULL,            -- 감성 카피
    tags                TEXT[],                   -- 키워드 태그 배열
    model_name          VARCHAR(100) NOT NULL,    -- 생성 모델명
    generated_at        TIMESTAMPTZ DEFAULT NOW(),
    expires_at          TIMESTAMPTZ DEFAULT NOW() + INTERVAL '7 days'
);
```

### 옵션 B: `serving.vod_recommendation` 에 컬럼 추가

```sql
ALTER TABLE serving.vod_recommendation
    ADD COLUMN recommendation_reason TEXT,
    ADD COLUMN recommendation_copy TEXT,
    ADD COLUMN copy_tags TEXT[];
```

**판단 기준**: 문구 재생성 주기가 추천 갱신 주기와 같으면 B, 독립적이면 A.

---

## Phase 계획

### Phase 0: 베이스라인 평가 (튜닝 전)

- 후보 모델 3~4종을 Ollama에서 zero-shot / few-shot 비교
- 평가 기준: 한국어 자연스러움, 톤 일관성, JSON 출력 안정성
- 베이스 모델 확정

### Phase 1: Seed 데이터 구축

- DB에서 실제 VOD 메타 추출 → Seed 템플릿 생성
- 추천 사유 유형별 10건씩 수작업 작성 (50~100건)
- 검수 및 포맷 통일

### Phase 2: 학습 데이터 증강

- GPT-4/Claude로 Seed 기반 500~1,000건 증강
- 사람 검수 (품질 필터)
- train/val 분리 (8:2)

### Phase 3: QLoRA 튜닝

- Colab 환경 세팅 (transformers + peft + trl)
- 학습 실행 + 하이퍼파라미터 탐색
- LoRA adapter 추출 → Ollama Modelfile 통합

### Phase 4: 파이프라인 구현

- `context_builder.py` — 추천 시그널 조립
- `copy_generator.py` — Ollama 호출 + JSON 파싱
- `quality_filter.py` — 출력 검증
- `batch_generate.py` — 배치 생성 + DB 적재

### Phase 5: 평가 및 반복

- 생성 결과 사람 평가 (1~5점)
- 나쁜 케이스 수정 → 재학습
- A/B 테스트 (zero-shot vs 튜닝 모델)

---

## 인터페이스 (Database_Design 등록 필요)

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `serving.vod_recommendation` | `recommendation_id`, `user_id_fk`, `vod_id_fk`, `recommendation_type`, `score` | 각종 | 추천 사유 분석 |
| `serving.popular_recommendation` | `genre`, `rank`, `vod_id_fk`, `score`, `recommendation_type` | 각종 | 인기/트렌딩 사유 |
| `public.vod` | `full_asset_id`, `asset_nm`, `genre`, `director`, `cast_lead`, `smry`, `release_date` | 각종 | VOD 메타데이터 |
| `public.watch_history` | `user_id_fk`, `vod_id_fk`, `strt_dt`, `completion_rate` | 각종 | 유저 시청 패턴 분석 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `serving.recommendation_copy` (신규) | `recommendation_id`, `recommendation_reason`, `recommendation_copy`, `tags`, `model_name` | 각종 | DB 스키마 확정 후 |

---

## 기술 스택

```python
# 학습
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer

# 추론 (로컬)
import ollama  # or requests to Ollama API

# 데이터
import psycopg2
import pandas as pd
import json
```

---

## 실행 환경

```bash
# 추론/파이프라인 (로컬)
conda activate myenv
pip install ollama pandas psycopg2-binary pyyaml

# 학습 (Colab)
pip install transformers peft trl bitsandbytes datasets accelerate
```

---

## 의존성

- CF_Engine, Vector_Search → 추천 결과가 `serving.vod_recommendation`에 있어야 함
- Database_Design → `serving.recommendation_copy` 스키마 확정 필요
- API_Server → 문구를 추천 응답에 포함하는 엔드포인트 수정 필요
