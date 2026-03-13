# VOD_Embedding — 팀원 협업 가이드

CLIP 임베딩 파이프라인 분산 작업을 위한 안내 문서입니다.

---

## 파이프라인 개요

```
[준비]    split_tasks.py        → data/tasks_A~D.json  (오너가 1회 실행)
            ↓
[PLAN_01] crawl_trailers.py   → trailers/*.webm        (트레일러 다운로드)
            ↓
[PLAN_02] batch_embed.py      → embeddings_*.parquet   (CLIP 임베딩)
            ↓
[PLAN_03] ingest_to_db.py     → vod_embedding 테이블   (오너가 적재)
```

팀원은 **PLAN_01 + PLAN_02**를 수행하고 parquet 파일을 제출합니다.
각자 할당된 `tasks_X.json`을 기반으로 작업하므로 DB 쓰기 권한은 불필요합니다.

---

## 환경 설정

```bash
conda activate myenv
pip install -r requirements.txt
```

CLIP 모델은 처음 실행 시 HuggingFace에서 자동 다운로드됩니다 (~340MB).
로컬 모델 경로가 있다면 `batch_embed.py` 상단 `MODEL_PATH` 변수를 수정하세요.

---

## 실행 방법

### 0. 작업 분할 파일 생성 (오너만 1회 실행)

전체 VOD를 4명 분량으로 나눈 JSON 파일을 생성합니다.

```bash
python scripts/split_tasks.py
# 출력: data/tasks_A.json ~ data/tasks_D.json
```

| 파일 | 내용 | 건수 |
|------|------|-----:|
| `tasks_A.json` | TV 연예/오락 (full_asset_id 정렬 앞 절반) | ~9,570 |
| `tasks_B.json` | TV 연예/오락 (full_asset_id 정렬 뒤 절반) | ~9,571 |
| `tasks_C.json` | 영화 + TV드라마 + 키즈 (시리즈 dedup) | ~11,508 |
| `tasks_D.json` | TV애니메이션 + TV 시사/교양 + 기타 + 교육 + 다큐 등 | ~11,102 |

생성된 `tasks_X.json`을 각 팀원에게 전달합니다.

---

### 1. 트레일러 다운로드 (PLAN_01)

받은 task 파일을 지정해 실행합니다. `X`는 본인 담당 팀(A/B/C/D).

```bash
python scripts/crawl_trailers.py --task-file data/tasks_X.json
```

중단 후 재시작 시 자동으로 이어서 처리됩니다 (`data/crawl_status.json` 체크포인트).

진행 상황 확인:

```bash
python scripts/crawl_trailers.py --status
```

### 2. 임베딩 실행 — parquet 출력 (PLAN_02)

트레일러 다운로드 완료 후 실행합니다. `이름`에 본인 이름을 넣어주세요.

```bash
python scripts/batch_embed.py --output parquet \
    --out-file data/embeddings_이름.parquet \
    --delete-after-embed
```

> `--delete-after-embed`: 임베딩 완료된 영상 파일을 즉시 삭제해 디스크를 절약합니다.

진행 상황 확인:

```bash
python scripts/batch_embed.py --status
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
