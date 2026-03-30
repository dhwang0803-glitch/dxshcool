# Colab 배치 생성 실행 가이드

> **노트북**: `gen_rec_sentence/scripts/colab_batch_generate.ipynb`
>
> **목적**: 추천 풀 VOD × 5 세그먼트 → results.parquet 생성 (오프라인 모드)

---

## 전체 흐름

```
┌─────────────────────────────────────────────────────┐
│  1. 로컬: export_for_colab.py                        │
│     → colab_data/vod_contexts.parquet 생성           │
│     → colab_data/existing_pairs.parquet 생성         │
│                                                      │
│  2. Google Drive에 업로드                             │
│     내 드라이브/dxshcool/ 폴더 통째로                  │
│                                                      │
│  3. Colab: batch_generate.py --offline               │
│     → colab_data/results.parquet 생성                │
│     (DB 접속 불필요, parquet 기반)                     │
│                                                      │
│  4. 로컬: ingest_results.py                          │
│     → results.parquet → serving.rec_sentence UPSERT  │
└─────────────────────────────────────────────────────┘
```

---

## 사전 준비 (로컬)

### 1. parquet 데이터 추출

```bash
conda activate myenv
python gen_rec_sentence/scripts/export_for_colab.py
```

출력:
```
gen_rec_sentence/data/colab_data/
├── vod_contexts.parquet      ← VOD 메타데이터 (~13K건)
└── existing_pairs.parquet    ← 이미 생성된 (vod_id, segment_id) 쌍
```

### 2. Google Drive에 업로드

```
내 드라이브/
└── dxshcool/                               ← 프로젝트 루트
    └── gen_rec_sentence/
        ├── src/
        │   ├── context_builder.py
        │   ├── sentence_generator.py
        │   └── quality_filter.py
        ├── scripts/
        │   └── batch_generate.py
        └── data/
            └── colab_data/
                ├── vod_contexts.parquet     ← export_for_colab.py 출력
                └── existing_pairs.parquet   ← export_for_colab.py 출력
```

**업로드 방법**:
1. [Google Drive](https://drive.google.com) 접속
2. `내 드라이브`에 `dxshcool` 폴더 생성
3. 로컬 `gen_rec_sentence/` 폴더를 통째로 드래그 앤 드롭

> `.env` 파일은 **업로드 불필요**. Colab에서 DB에 접속하지 않는다.

---

## Colab 실행 가이드

### GPU 런타임 설정 (필수)

1. 상단 메뉴: `런타임` → `런타임 유형 변경`
2. **하드웨어 가속기**: `GPU` 선택
3. **GPU 유형**: `A100` 선택 (Colab Pro 필요)
   - A100 (40GB): 12B/27B 모두 가능
   - T4 (16GB): 12B만 가능
4. `저장` 클릭

### 셀 실행 방법

- `Shift + Enter`: 실행 후 다음 셀 이동
- `Ctrl + Enter`: 실행, 현재 셀 유지

### 1단계: Ollama 설치 + 모델 다운로드

| 셀 | 내용 | 예상 시간 |
|----|------|----------|
| 셀 1 | Ollama 설치 | ~30초 |
| 셀 2 | Ollama 서버 실행 | ~3초 |
| 셀 3 | 12B + 27B 모델 다운로드 | ~8분 (합계 ~26GB) |
| 셀 4 | `ollama list` 확인 | 즉시 |

### 2단계: Google Drive 마운트 + 의존성

| 셀 | 내용 |
|----|------|
| 셀 5 | Drive 마운트 (팝업에서 계정 승인) + 경로 확인 |
| 셀 6 | pip install (ollama, pandas, pyarrow) |
| 셀 7 | 작업 디렉토리 설정 |

셀 5에서 `PROJECT_ROOT` 경로를 본인 Drive 구조에 맞게 수정:
```python
PROJECT_ROOT = "/content/drive/MyDrive/dxshcool"  # 기본값
```

`vod_contexts.parquet` 없으면 에러 → 로컬에서 `export_for_colab.py` 먼저 실행.

### 3단계: 데이터 확인

| 셀 | 내용 |
|----|------|
| 셀 8 | VOD 건수, ct_cl 분포, 기존 쌍 건수 확인 |

출력 예시:
```
VOD 컨텍스트: 13,181건
전체 생성 대상: 65,905쌍 (VOD × 5 seg)

ct_cl 분포:
TV드라마        4,521
영화            3,892
TV 연예/오락    2,341
TV애니메이션    1,527
키즈              900
```

### 4단계: 12B vs 27B 비교 (선택)

| 셀 | 내용 | 예상 시간 |
|----|------|----------|
| 셀 9 | 두 모델로 10건씩 생성 | ~2분 |
| 셀 10 | 나란히 비교 출력 + 길이 통계 | 즉시 |

**판단 기준**:
- 27B가 한국어 자연스러움·환각 감소에서 확실히 좋다 → 27B
- 비슷하다 → 12B (속도 2배 빠름)

### 5단계: 배치 생성

```python
# 소규모 테스트 (10건)
!python gen_rec_sentence/scripts/batch_generate.py \
    --offline gen_rec_sentence/data/colab_data \
    --model gemma3:12b-it-qat \
    --limit 10

# 전체 배치 (27B 선택 시 --model gemma3:27b-it-qat)
!python gen_rec_sentence/scripts/batch_generate.py \
    --offline gen_rec_sentence/data/colab_data \
    --model gemma3:12b-it-qat
```

| 모델 | 예상 시간 |
|------|----------|
| 12B | ~2-3시간 |
| 27B | ~5-7시간 |

**진행 로그** (200건마다):
```
진행: 200/65905 | 성공 187 / 실패 13 | 저장 완료
진행: 400/65905 | 성공 381 / 실패 19 | 저장 완료
```

> **세션 끊김 대비**: 200건마다 `results.parquet`에 자동 저장.
> 재실행하면 이전 결과를 자동으로 이어받아 생성.

### 6단계: 결과 확인

세그먼트별 건수, 평균 길이, 랜덤 샘플 10건 출력.

---

## 세션 끊김 대응

### 재개 방법

```
1. 새 런타임 시작
2. 셀 1~7 재실행 (Ollama + Drive + 의존성)
3. 전체 배치 셀 재실행 → 자동으로 이전 결과 이어받기
```

`results.parquet`이 Drive에 저장되므로 런타임 초기화해도 데이터 유지.

### Colab 세션 제한

| 상황 | 대응 |
|------|------|
| 90분 유휴 → 연결 해제 | 브라우저 탭 열어두고 가끔 클릭 |
| 12시간 최대 실행 | 12B 기준 2-3h이므로 충분. 27B도 7h 이내 |
| GPU 할당 실패 | 시간대 변경 (새벽), 또는 T4로 전환 (12B만) |

---

## 배치 완료 후 (로컬)

### 1. results.parquet 다운로드

Google Drive에서 `gen_rec_sentence/data/colab_data/results.parquet` 다운로드.
또는 Drive 동기화 앱 사용 시 자동 반영.

### 2. DB 적재

```bash
conda activate myenv

# 적재 전 확인 (DB 쓰기 없음)
python gen_rec_sentence/scripts/ingest_results.py \
    gen_rec_sentence/data/colab_data/results.parquet --dry-run

# 실제 적재
python gen_rec_sentence/scripts/ingest_results.py \
    gen_rec_sentence/data/colab_data/results.parquet
```

### 3. 사후검증

```
Stage 1: quality_filter (기존 규칙) → PASS/FAIL
Stage 2: konlpy 명사 추출 + 메타데이터 교차검증 → FLAG/CLEAN
Stage 3: FLAG 건만 수동/LLM 리뷰 → APPROVE/REJECT
```

상세: `EXPLORATION_LOG.md` §16

---

## 요약 체크리스트

```
[ ] 로컬: export_for_colab.py 실행 → parquet 생성
[ ] Google Drive에 gen_rec_sentence/ 업로드
[ ] Colab: GPU 런타임 설정 (A100 권장)
[ ] Colab: Ollama 설치 + 모델 다운로드
[ ] Colab: Drive 마운트 + 데이터 확인
[ ] Colab: 12B vs 27B 비교 → 모델 결정
[ ] Colab: 소규모 테스트 (10건)
[ ] Colab: 전체 배치 실행
[ ] Colab: 결과 확인
[ ] 로컬: results.parquet 다운로드
[ ] 로컬: ingest_results.py → DB 적재
[ ] 로컬: 사후검증 파이프라인 실행
```
