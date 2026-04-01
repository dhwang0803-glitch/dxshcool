CF_Engine 추천 정확도 평가를 실행하고 보고서를 작성해줘.

---

## 목적

유저당 VOD 추천 점수를 수치화하여 모델이 얼마나 정확하게 추천하는지 평가하고,
평가 보고서를 `CF_Engine/docs/` 에 저장한다.

---

## 실행 순서

### 1. 환경 확인

```bash
cd CF_Engine
```

현재 브랜치가 `CF_Engine`인지 확인한다.

---

### 2. 종합 평가 실행 (필터 전/후 비교)

```bash
C:/Users/user/miniconda3/envs/myenv/python.exe scripts/full_eval.py --k 10
```

- 필터 없음(27.9% 혼합)과 필터 ON(고품질만) 두 가지를 자동으로 비교 실행
- 결과: `docs/full_eval_report_YYYYMMDD_HHMMSS.md` 자동 저장

측정 지표:

| 지표 | 의미 |
|------|------|
| NDCG@10 | 추천 순위의 질 — 정답이 상위에 있을수록 높음 (0.3 이상이면 좋음) |
| MRR | 정답이 처음 등장하는 순위의 역수 평균 (0.2 이상이면 좋음) |
| HitRate@10 | Top-10 안에 정답이 1개라도 있는 유저 비율 (0.6 이상이면 좋음) |
| Precision@10 | 추천 10개 중 정답 비율 |
| Coverage | 전체 아이템 중 추천에 등장하는 비율 (다양성) |

---

### 3. 유저별 점수 급락 지점 분석

```bash
# 필터 없음 (27.9% 혼합) 기준
C:/Users/user/miniconda3/envs/myenv/python.exe scripts/score_cutoff_analysis.py --users 500 --top-k 20

# 필터 ON 기준
C:/Users/user/miniconda3/envs/myenv/python.exe scripts/score_cutoff_analysis.py --users 500 --top-k 20 --filter-quality
```

- 유저별로 "명확한 추천 구간"과 "리스트 채우기 구간"의 경계를 탐지
- 결과: `docs/score_cutoff_report_YYYYMMDD_HHMMSS.md`, `docs/score_cutoff_analysis.png`

---

### 4. 육안 검증 (20명 샘플)

```bash
C:/Users/user/miniconda3/envs/myenv/python.exe scripts/inspect_recommendations.py --users 20 --top-k 10
```

- 유저별 시청 이력과 추천 결과를 나란히 출력
- 결과: `docs/inspect_result_YYYYMMDD_HHMMSS.md` 자동 저장

---

### 5. 평가 보고서 작성

위 1~4 단계 결과를 종합하여 아래 형식으로 `docs/eval_report_final_YYYYMMDD.md` 를 작성한다.

```markdown
# CF_Engine 추천 정확도 평가 보고서

- 일시: YYYY-MM-DD
- 모델: ALS (factors=128, iterations=20, regularization=0.01, alpha=40)

## 1. 핵심 지표 요약

| 지표 | 필터 없음 | 필터 ON | 변화 | 기준 |
|------|---------|---------|------|------|
| NDCG@10 | ... | ... | ... | 0.3 이상이면 좋음 |
| MRR | ... | ... | ... | 0.2 이상이면 좋음 |
| HitRate@10 | ... | ... | ... | 0.6 이상이면 좋음 |
| Precision@10 | ... | ... | ... | - |
| Coverage | ... | ... | ... | 높을수록 다양 |

## 2. 유저별 점수 분석

- 급락 지점 중앙값: K=?위
- 75% 유저 커버 K: ?
- 90% 유저 커버 K: ?
- 권장 K: ?

## 3. 세그먼트별 성능

| 세그먼트 | NDCG@10 | HitRate@10 | 평가 |
|----------|---------|------------|------|
| Cold (2~4개) | ... | ... | ... |
| Warm (5~19개) | ... | ... | ... |
| Hot (20개+) | ... | ... | ... |

## 4. 육안 검증 결과

| 등급 | 유저 수 | 비율 |
|------|---------|------|
| ★★★★★ 매우 좋음 | ... | ... |
| ★★★★☆ 좋음 | ... | ... |
| ★★★☆☆ 보통 | ... | ... |

## 5. 종합 판단

- 현재 모델 성능 수준: (좋음 / 보통 / 개선 필요)
- 주요 강점: ...
- 주요 약점: ...
- 권장 K 및 폴백 전략: ...
- 다음 단계: ...
```

---

### 6. 커밋

```bash
git add CF_Engine/docs/
git commit -m "docs(CF_Engine): 추천 정확도 평가 보고서 YYYYMMDD"
```

---

## 주의사항

- `myenv` Python 환경만 사용 (`C:/Users/user/miniconda3/envs/myenv/python.exe`)
- 실행 디렉토리는 반드시 `CF_Engine/` 내부
- `.env` 파일은 읽지 않으며 환경변수로만 DB 접속
- 평가 실행 중 DB 쓰기 없음 (읽기 전용)
