# gen_rec_sentence — Claude Code 브랜치 지침

> 루트 `CLAUDE.md` 보안 규칙과 함께 적용된다.

## 모듈 역할

**VOD 감성 카피 생성 파이프라인** — VOD 메타데이터 + CLIP 영상 임베딩(visualized vector)을
조합하여, 홈 배너 포스터 하단에 표시할 **감성 문구(rec_sentence)**를 LLM으로 생성한다.

### 비즈니스 목적

유저가 시리즈 상세 페이지까지 진입해서 줄거리·스틸샷을 확인하고 결제를 결정하면
**구매 전환율이 떨어진다.** 포스터 + 추천 문구만으로 시청 결정을 유도하는 것이 목표.

문구가 해야 하는 일:
1. **시각화** — "이 VOD를 보면 어떤 영상을 보게 될지" 장면을 떠올리게 한다
2. **기대감 형성** — 감성적 톤으로 시청 욕구를 자극한다
3. **브랜드 활용** — 감독명·배우명 등 네임밸류가 있는 요소는 적극 언급한다
   (예: "크리스토퍼 놀란", "봉준호" 등 이름만으로 기대감을 높이는 경우)

### 생성 예시

> 덩케르크 포스터 하단:
> "총알이 빗발치는 해변, 탈출을 위한 필사적인 항해.
> 하늘을 덮은 적의 그림자. 절망 속에서 피어나는 인간의 의지"

### pattern_reason과의 차이

| 구분 | pattern_reason (기존) | rec_sentence (이 브랜치) |
|------|----------------------|-------------------------|
| 성격 | 추천 사유 설명 (왜 추천?) | VOD 콘텐츠 자체의 **감성 카피** (무슨 작품?) |
| 입력 | 시청 이력 + 태그 매칭 | **VOD 메타데이터 + CLIP 임베딩** |
| 톤 | "봉준호 감독 작품을 즐겨 보셨어요" | 영화적·시적 장면 묘사 |
| 용도 | 추천 카드 선정이유 | 홈 배너 포스터 하단 카피 |
| 유저 의존 | O (유저별 다름) | X (VOD당 1건, 유저 무관) |

---

## 파이프라인 아키텍처

```
[1] 컨텍스트 조립 — context_builder.py
    DB에서 직접 읽기:
      - public.vod → 메타데이터 (genre, smry, director, cast_lead, rating 등)
      - public.vod_embedding → CLIP 영상 임베딩 (512d, 이미 적재 완료)
    → LLM 입력용 JSON/프롬프트 구성

[2] 문구 생성 — sentence_generator.py
    튜닝된 LLM (Ollama 로컬) 또는 API 호출
    → rec_sentence (2문장, 감성 카피) 생성

[3] 품질 필터 — quality_filter.py
    - 길이 제약 (20~120자)
    - 금칙어 필터
    - 메타데이터 사실 검증 (장르/감독명 일치 여부)
    - JSON 파싱 성공 여부

[4] DB 적재 — batch_generate.py
    → serving.rec_sentence 테이블 UPSERT
```

> **시각 정보 별도 추출 불필요** — VOD_Embedding 브랜치에서 CLIP ViT-B/32 기반
> 영상 임베딩을 이미 `vod_embedding` 테이블에 적재 완료. 이 벡터를 그대로 LLM 입력에 포함한다.

---

## 튜닝 전략

### 베이스 모델

**Gemma 2 9B** (확정 — Phase 0 zero-shot 비교 결과)

| 후보 | 결과 | 탈락 사유 |
|------|------|----------|
| **Gemma 2 9B** | **채택** | 장면 시각화 우수, 영상 속 상황을 떠올리게 하는 톤 |
| EXAONE 3.5 7.8B | 탈락 | 인물 홍보 톤 ("감독의 독보적인~"), 영상 기대감 약함 |
| Qwen 2.5 7B | 탈락 | 영어 혼입("wager"), 사실 오류, 추상적 표현 |

### 튜닝 방식

**DoRA + QLoRA** (Colab Pro 환경)

| 기법 | 목적 | 설정 |
|------|------|------|
| DoRA + QLoRA | 지식 유실 방지 | `use_dora=True` in peft LoraConfig |
| Replay Buffer | 기존 한국어 능력 유지 | 일반 한국어 대화 데이터 10~20% 혼합 |
| Unsloth + RSLoRA | 학습 속도 + 안정성 | Unsloth 최적화 LoRA 활용 |

- 4-bit 양자화 + LoRA rank 16~32
- 학습 환경: Google Colab Pro (T4/A100)
- 프레임워크: `unsloth` + `peft` + `trl` (SFTTrainer)
- 출력: LoRA adapter (~50MB) → Ollama Modelfile로 통합
- 추론 환경: 로컬 Ollama (CPU 양자화 모델)

### 학습 데이터

| 단계 | 건수 | 방식 |
|------|------|------|
| Seed | 50~100건 | 수작업 (Gold Standard) |
| 증강 | 500~1,000건 | GPT-4/Claude few-shot 생성 + 사람 검수 |
| 반복 개선 | +α | 튜닝 모델 출력 평가 → 나쁜 케이스 수정 추가 |

### 학습 데이터 포맷 (Instruction Tuning)

```json
{
  "instruction": "VOD의 메타데이터와 시각 키워드를 바탕으로 포스터 하단에 표시할 감성 문구를 생성하세요.",
  "input": {
    "asset_nm": "덩케르크",
    "genre": "전쟁/액션",
    "director": "크리스토퍼 놀란",
    "smry": "2차 세계대전, 덩케르크 해변에 고립된 40만 연합군 병사들의 탈출 작전...",
    "embedding": [0.0234, -0.0512, 0.0891, "...(CLIP 512d 벡터)"]
  },
  "output": {
    "rec_sentence": "총알이 빗발치는 해변, 탈출을 위한 필사적인 항해.\n하늘을 덮은 적의 그림자. 절망 속에서 피어나는 인간의 의지"
  }
}
```

---

## Phase 계획

| Phase | 내용 |
|-------|------|
| 0 | 베이스 모델 zero-shot 비교 (Ollama) |
| 1 | Seed 데이터 수작업 50~100건 (DB에서 VOD 메타 + 임베딩 조회) |
| 2 | LLM 증강 500~1,000건 + 사람 검수 |
| 3 | QLoRA 튜닝 (Colab) |
| 4 | 파이프라인 구현 (컨텍스트 조립 → 생성 → 품질 필터 → DB 적재) |
| 5 | 평가 및 반복 (사람 평가 1~5점 + A/B 비교) |

---

## 폴더 구조

```
gen_rec_sentence/
├── src/
│   ├── context_builder.py           ← DB에서 VOD 메타 + 임베딩 조회 → LLM 입력 조립
│   ├── sentence_generator.py        ← Ollama 호출 (프롬프트 구성 + JSON 파싱)
│   └── quality_filter.py            ← 생성 결과 검증 (길이/금칙어/사실 확인)
├── scripts/
│   ├── build_seed_data.py           ← DB에서 VOD 메타 + 임베딩 조회 → Seed 템플릿
│   ├── augment_training_data.py     ← LLM으로 학습 데이터 증강
│   ├── train_lora.py                ← QLoRA 학습 (Colab용)
│   ├── evaluate_model.py            ← 튜닝 전후 품질 비교
│   └── batch_generate.py            ← 배치 문구 생성 → DB 적재
├── data/
│   ├── seed_examples.jsonl          ← 수작업 Seed 50~100건
│   ├── training_data.jsonl          ← 증강 완료 학습 데이터
│   └── eval_results.jsonl           ← 평가 결과
├── config/
│   ├── generation_config.yaml       ← 모델, 프롬프트 템플릿, 길이 제약
│   └── .env.example                 ← DB 접속 정보 템플릿
├── tests/
│   ├── test_context_builder.py
│   ├── test_sentence_generator.py
│   └── test_quality_filter.py
└── docs/
    └── plans/                       ← Phase별 PLAN 문서
```

---

## 인터페이스

### 업스트림 (읽기)

| 테이블 | 컬럼 | 타입 | 용도 |
|--------|------|------|------|
| `public.vod` | `full_asset_id`, `asset_nm`, `ct_cl` | VARCHAR | 대상 VOD 식별 + 콘텐츠명 |
| `public.vod` | `genre`, `genre_detail`, `director` | VARCHAR | 장르·감독 메타데이터 → 컨텍스트 조립 |
| `public.vod` | `cast_lead`, `smry`, `rating` | TEXT/VARCHAR | 출연진·줄거리·등급 → 컨텍스트 조립 |
| `public.vod` | `poster_url` | TEXT | 포스터 존재 여부 필터 (배너 노출 대상만) |
| `public.vod_embedding` | `vod_id_fk`, `embedding` | VARCHAR/VECTOR(512) | CLIP 영상 벡터 (이미 적재 완료) → LLM 입력에 직접 포함 |

### 다운스트림 (쓰기)

| 테이블 | 컬럼 | 타입 | 비고 |
|--------|------|------|------|
| `serving.rec_sentence` (신규) | `vod_id_fk` | VARCHAR(64) | FK → vod.full_asset_id, UNIQUE |
| `serving.rec_sentence` | `rec_sentence` | TEXT | 생성된 감성 카피 (2문장) |
| `serving.rec_sentence` | `embedding_used` | BOOLEAN | 임베딩 입력 사용 여부 |
| `serving.rec_sentence` | `model_name` | VARCHAR(100) | 생성 모델명 |
| `serving.rec_sentence` | `generated_at` | TIMESTAMPTZ | 생성 시각 |
| `serving.rec_sentence` | `expires_at` | TIMESTAMPTZ | TTL (기본 30일) |

> DDL은 Database_Design 브랜치와 협의 후 확정. 위 스키마는 초안.

---

## 의존성

- **VOD_Embedding** → `vod_embedding` 테이블에 CLIP 벡터가 적재되어 있어야 함
- **RAG** → `vod` 테이블에 `smry`, `director`, `cast_lead` 등 메타가 채워져 있어야 함
- **Database_Design** → `serving.rec_sentence` DDL 확정 필요
- **API_Server** → 홈 배너 응답에 `rec_sentence` 필드 추가 필요

---

## 실행 환경

```bash
# 추론 (로컬, CPU)
# Ollama 설치: https://ollama.com/download
conda activate myenv
pip install ollama pandas psycopg2-binary pyyaml numpy

# 학습 (Colab Pro)
pip install unsloth peft trl bitsandbytes datasets accelerate
# Unsloth가 transformers를 내부적으로 관리하므로 별도 설치 불필요
```

---

## 기술 스택

```python
# 문구 생성
import ollama  # Ollama 로컬 LLM 호출

# DB
import psycopg2
import pandas as pd
import numpy as np
```
