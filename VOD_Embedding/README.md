# VOD_Embedding — 팀원 협업 가이드

CLIP 임베딩 파이프라인 분산 작업을 위한 안내 문서입니다.

---

## 파이프라인 개요

```
[PLAN_01] crawl_trailers.py   → trailers/*.webm   (트레일러 다운로드)
[PLAN_02] batch_embed.py      → embeddings_*.parquet  (CLIP 임베딩)  ← 팀원 담당
[PLAN_03] ingest_to_db.py     → vod_embedding 테이블  (오너가 적재)
```

팀원은 **PLAN_02만** 수행하고 결과 parquet 파일을 제출합니다.
DB 쓰기 권한 없이도 작업 가능합니다.

---

## 환경 설정

```bash
conda activate myenv
pip install sentence-transformers opencv-python pillow pandas pyarrow
```

CLIP 모델은 처음 실행 시 HuggingFace에서 자동 다운로드됩니다 (~340MB).
로컬 모델 경로가 있다면 `batch_embed.py` 상단 `MODEL_PATH` 변수를 수정하세요.

---

## 실행 방법

### 1. 트레일러 다운로드 (PLAN_01)

담당 vod_id 범위의 트레일러를 먼저 수집합니다.

```bash
python pipeline/crawl_trailers.py --trailers-dir ./trailers
```

### 2. 임베딩 실행 — parquet 출력 (PLAN_02)

```bash
# 기본 (data/embeddings_output.parquet 저장)
python pipeline/batch_embed.py --output parquet --trailers-dir ./trailers

# 파일명에 본인 이름 포함 (권장)
python pipeline/batch_embed.py --output parquet \
    --out-file embeddings_홍길동.parquet \
    --trailers-dir ./trailers
```

> **주의**: `--output pkl` (기본값)은 DB 직접 적재용이므로 팀원은 반드시 `--output parquet`을 사용하세요.

### 3. 진행 상황 확인

```bash
python pipeline/batch_embed.py --status
```

---

## 출력 파일 스펙

| 항목 | 내용 |
|------|------|
| 포맷 | `.parquet` |
| 컬럼 1 | `vod_id` (str) — DB `vod_id_fk`와 동일 |
| 컬럼 2 | `embedding` (list of float32, 길이 512) |
| 파일명 | `embeddings_{본인이름}.parquet` |

### 예시

```python
import pandas as pd
df = pd.read_parquet("embeddings_홍길동.parquet")
print(df.dtypes)
# vod_id       object
# embedding    object  (list of float32)

print(len(df["embedding"][0]))  # 512
```

---

## 제출 전 검증

제출 전 반드시 아래 코드로 검증하세요. 오류가 없어야 합니다.

```python
import pandas as pd

df = pd.read_parquet("embeddings_홍길동.parquet")

# 1. NULL 체크
assert df["embedding"].notna().all(), "NULL 행 존재"

# 2. 벡터 차원 체크
assert df["embedding"].apply(len).eq(512).all(), "512차원 아닌 행 존재"

# 3. vod_id 중복 체크
assert df["vod_id"].is_unique, "vod_id 중복 존재"

print(f"검증 완료: {len(df):,}건")
```

---

## 제출 방법

완성된 parquet 파일을 오너(프로젝트 관리자)에게 전달합니다.
파일명에 본인 이름을 포함해주세요: `embeddings_{이름}.parquet`

---

## 자주 묻는 질문

**Q. DB 접속 정보가 없어도 되나요?**
네. parquet 출력 모드는 DB를 전혀 사용하지 않습니다.

**Q. 중간에 실패한 VOD는 어떻게 되나요?**
실패한 VOD는 건너뛰고 성공한 것만 parquet에 저장됩니다. `data/embed.log`에서 실패 목록을 확인할 수 있습니다.

**Q. 모델이 없을 때 어떻게 하나요?**
`MODEL_PATH`에 지정된 로컬 경로가 없으면 HuggingFace Hub에서 자동으로 `clip-ViT-B-32`를 다운로드합니다.
