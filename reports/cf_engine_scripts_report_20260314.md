# CF_Engine scripts/ 코드 분석 리포트 — 2026-03-14

---

## 파일 목록

```
CF_Engine/scripts/
├── train.py          ← 메인 실행 (파이프라인 통합)
├── export_to_db.py   ← DB 저장 담당
├── evaluate.py       ← 성능 평가 (NDCG/MRR/HitRate)
└── pilot_test.py     ← 초기 검증 테스트
```

---

## 1. train.py — 메인 실행 파일

### 한 줄 요약
> src/ 모듈 3개를 순서대로 호출해서 전체 파이프라인을 실행하는 진행자(orchestrator).

### 실행 방법
```bash
python scripts/train.py                          # DB 학습 + 적재 (조장 전용)
python scripts/train.py --config config/als_config.yaml  # 설정 파일 지정
python scripts/train.py --dry-run               # DB 저장 없이 결과만 확인
```

### 내부 동작 순서
```
1. als_config.yaml 읽기 (하이퍼파라미터 로드)
2. DB 접속
3. load_matrix()  → 희소 행렬 + 인코더 5개
4. train()        → ALS 모델 학습
5. recommend_all()→ 전체 유저 Top-20 추천 생성
6. build_records()→ 인덱스 → DB 레코드 변환
7. [분기]
   --dry-run → "DB 저장 생략" 로그만 출력
   일반 실행 → export() 호출 → DB 저장
8. 결과 로그 출력 (유저 수, 아이템 수, 추천 건수, 소요 시간)
```

### 중요 코드 포인트

| 라인 | 내용 | 설명 |
|------|------|------|
| 43 | `--dry-run` 옵션 정의 | DB 저장 없이 테스트 |
| 61 | `load_matrix(conn, alpha=m["alpha"])` | alpha=40 적용 |
| 68 | `recommend_all(model, mat, top_k=r["top_k"])` | top_k=20 |
| 80 | `if args.dry_run:` | dry-run 분기 |
| 83 | `export(conn, records, ...)` | 실제 DB 저장 |

### ⚠️ 미구현 사항
- `--output parquet` : 팀원용 (DB 없이 parquet 저장)
- `--from-parquet` : 조장용 (parquet → DB 적재)

---

## 2. export_to_db.py — DB 저장 파일

### 한 줄 요약
> 기존 CF 추천을 지우고 새 추천으로 덮어쓰는 파일. train.py 내부에서 호출됨.

### 실행 방법
```bash
# 직접 실행 X — train.py에서 내부적으로 호출됨
from export_to_db import export
export(conn, records, batch_size=1000, recommendation_type="COLLABORATIVE")
```

### 내부 동작 순서
```
1. records에서 user_id_fk 목록 추출
2. DELETE: 해당 유저들의 기존 CF 추천 삭제
3. INSERT: 신규 추천 배치 삽입 (1,000건씩)
4. commit
```

### SQL 구조
```sql
-- STEP 1: 기존 삭제
DELETE FROM serving.vod_recommendation
WHERE recommendation_type = 'COLLABORATIVE'
  AND user_id_fk = ANY(유저목록)

-- STEP 2: 신규 삽입 (배치 1,000건)
INSERT INTO serving.vod_recommendation
  (user_id_fk, vod_id_fk, rank, score, recommendation_type)
VALUES (...)
```

### 왜 DELETE + INSERT 패턴인가?
- `serving.vod_recommendation`의 UNIQUE 제약이 `(user_id_fk, vod_id_fk)` 기준
- recommendation_type이 UNIQUE에 포함 안 됨 → UPSERT 불가
- 안전하게 지우고 새로 넣는 방식 채택

---

## 3. evaluate.py — 성능 평가 파일

### 한 줄 요약
> "추천이 얼마나 정확한가"를 수치로 측정하는 파일. NDCG / MRR / HitRate 계산.

### 실행 방법
```bash
python scripts/evaluate.py               # 기본 실행 (k=20)
python scripts/evaluate.py --k 20       # Top-K 지정
```

### 내부 동작 순서
```
1. DB에서 watch_history 로드
2. Hold-out 분리
   - 각 유저의 마지막 시청 1건 → 테스트셋 분리
   - 나머지 → 학습셋
3. 학습셋으로 ALS 학습
4. 테스트 유저에게 추천 생성
5. 성능 지표 계산
6. docs/eval_report_YYYYMMDD_HHMMSS.md 저장
```

### 성능 지표 설명

| 지표 | 의미 | 예시 |
|------|------|------|
| **NDCG@K** | 추천 순위 가중 정확도. 상위 순위일수록 점수 높음 | 1위에 정답 있으면 1.0, 하위일수록 낮아짐 |
| **MRR** | 정답이 몇 위에 있는지 역수의 평균 | 1위=1.0, 2위=0.5, 3위=0.33 |
| **HitRate@K** | Top-K 안에 정답이 있는 유저 비율 | 0.7 = 70% 유저에게 정답 포함 |

### Hold-out이란?
```
전체 시청 이력
  → 유저별 마지막 시청 1건 빼서 정답으로 저장
  → 나머지로 모델 학습
  → "빼놓은 정답"을 추천했는지 확인
```

### 출력 예시
```
docs/eval_report_20260314_153000.md

| 지표 | 값 |
|------|----|
| NDCG@20 | 0.1234 |
| MRR | 0.0987 |
| HitRate@20 | 0.2345 |
| eval_users | 198432 |
```

---

## 4. pilot_test.py — 파일럿 테스트 파일

### 한 줄 요약
> 본격 실행 전 "이 환경에서 돌아가나?" 확인용. 5,000명 샘플로 속도 측정.

### 실행 방법
```bash
python scripts/pilot_test.py
```

### 내부 동작 순서
```
STEP 1. watch_history 전체 규모 확인 + 5,000명 샘플 로드
STEP 2. User-Item 희소 행렬 구성 (alpha=40)
STEP 3. ALS 학습 (factors=64, iterations=10) — 속도 측정
STEP 4. 100명 샘플에 Top-20 추천 생성 — 속도 측정
STEP 5. 추천된 VOD의 poster_url 커버리지 확인
        (포스터 있는 비율 → UI 표시 가능 여부 판단)
마지막. 전체 데이터 학습 시간 추정 (factors=128, iter=20 기준)
```

### 출력 예시
```
=======================================================
  CF_Engine 파일럿 테스트
=======================================================
[STEP 1] watch_history 로드 (샘플 유저 5,000명)
  전체 규모: 3,992,530행 / 242,702유저 / 166,159아이템
  샘플 로드: 82,450행 (3.2초)

[STEP 2] User-Item 희소 행렬 구성 (alpha=40)
  행렬: 5,000 x 45,231  |  희소성: 99.96%  |  0.12초

[STEP 3] ALS 학습 (factors=64, iterations=10)
  학습 완료: 4.3초  |  속도: 11,628 user-iter/초

[STEP 4] 추천 생성 (Top-20, 샘플 100명)
  추천 완료: 892명/초  |  고유 추천 VOD: 1,847건

[STEP 5] poster_url 커버리지
  전체 VOD:  166,159건 중 0건 (0.0%) poster_url 보유
  추천 VOD:  1,847건 중 0건 (0.0%) poster_url 보유

=======================================================
  총 소요: 12.1초
  전체 데이터 학습 시간 추정 (factors=128, iter=20): ~0.7분
=======================================================
```

### ⚠️ 보안 주의
- `pilot_test.py`의 `get_conn()` 함수가 `.env` 파일을 직접 읽는 방식 사용
- 실제 운영에서는 `src/data_loader.py`의 `get_conn()` (os.getenv 방식) 사용할 것
- pilot_test.py는 개발 초기 검증 전용으로만 사용

---

## 5. 파일 간 관계도

```
train.py (메인 orchestrator)
  │
  ├── import src/data_loader.py
  │     └── get_conn()      — DB 접속
  │     └── load_matrix()   — 희소 행렬 생성
  │
  ├── import src/als_model.py
  │     └── train()         — ALS 학습
  │     └── recommend_all() — 추천 생성
  │
  ├── import src/recommender.py
  │     └── build_records() — 레코드 변환
  │
  ├── import scripts/export_to_db.py
  │     └── export()        — DB 저장
  │
  └── config/als_config.yaml
        └── 하이퍼파라미터 읽기

evaluate.py (독립 실행)
  ├── import src/data_loader.py
  └── import src/als_model.py

pilot_test.py (독립 실행 — 자체 get_conn 포함)
```

---

## 6. 실행 순서 가이드

```
개발/검증 단계
  Step 1. python scripts/pilot_test.py     ← 환경 확인
  Step 2. python scripts/train.py --dry-run ← 파이프라인 확인 (DB 저장 X)
  Step 3. python scripts/evaluate.py --k 20 ← 성능 측정

운영 적재 (조장 전용)
  Step 4. python scripts/train.py           ← 실제 DB 적재
```

---

## 7. 미결 사항 (추후 구현 필요)

| 옵션 | 용도 | 상태 |
|------|------|------|
| `--output parquet` | 팀원이 DB 없이 parquet 저장 | 🔲 미구현 |
| `--from-parquet <파일>` | 조장이 parquet → DB 적재 | 🔲 미구현 |
