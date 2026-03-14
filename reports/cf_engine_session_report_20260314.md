# CF_Engine 작업 세션 리포트 — 2026-03-14

---

## 1. 세션 요약

| 항목 | 내용 |
|------|------|
| 브랜치 | `CF_Engine` |
| 작업일 | 2026-03-14 |
| 핵심 작업 | `train.py` 미구현 옵션 2개 완성 |
| 테스트 | dry-run + parquet 저장 모두 통과 |
| PR | #25 OPEN |

---

## 2. 작업 전 상태

```
✅ 완료되어 있던 것
  src/data_loader.py     — DB → 희소 행렬 변환
  src/als_model.py       — ALS 학습 + 추천 생성
  src/recommender.py     — 결과 → DB 레코드 변환
  scripts/export_to_db.py— DB 저장 (DELETE + INSERT)
  scripts/evaluate.py    — 성능 평가 (NDCG/MRR/HitRate)
  scripts/pilot_test.py  — 파일럿 테스트
  config/als_config.yaml — 하이퍼파라미터
  tests/ 9/9 PASSED

🔲 미구현이었던 것
  scripts/train.py --output parquet   ← 팀원용
  scripts/train.py --from-parquet     ← 조장용
```

---

## 3. 오늘 구현 내용

### `scripts/train.py` 수정

#### 추가된 옵션

| 옵션 | 대상 | 동작 |
|------|------|------|
| `--output parquet` | 팀원 (DB 쓰기 권한 없음) | 추천 결과를 parquet 파일로 저장 |
| `--from-parquet <파일>` | 조장 | parquet 파일을 받아 DB에 적재 |

#### 추가된 함수

| 함수 | 역할 |
|------|------|
| `run_pipeline()` | DB 로드 → ALS 학습 → 추천 생성 공통 흐름 분리 |
| `save_parquet()` | 추천 레코드 → parquet 저장 (pyarrow) |
| `load_parquet()` | parquet → 추천 레코드 로드 (pyarrow) |

#### 전체 실행 모드 (4가지)

```bash
# 모드 1: 팀원용 — parquet 저장
python scripts/train.py --output parquet
→ data/cf_recommendations_20260314.parquet 생성

# 모드 2: 조장용 — parquet → DB 적재
python scripts/train.py --from-parquet data/cf_recommendations_20260314.parquet
→ serving.vod_recommendation 저장

# 모드 3: dry-run — DB 저장 없이 결과 확인
python scripts/train.py --dry-run

# 모드 4: 조장용 — DB 직접 학습 + 적재
python scripts/train.py
```

---

## 4. 테스트 결과

### dry-run

| 항목 | 결과 |
|------|------|
| 유저 수 | 242,702명 |
| 아이템 수 | 166,159개 |
| 추천 레코드 | 4,854,040건 |
| 소요 시간 | 191초 (~3.2분) |
| DB 저장 | 생략 (dry-run) |
| 결과 | ✅ 정상 |

### --output parquet

| 항목 | 결과 |
|------|------|
| 추천 레코드 | 4,854,040건 |
| 저장 파일 | `data/cf_recommendations_20260314.parquet` |
| 소요 시간 | 205초 (~3.4분) |
| 결과 | ✅ 정상 |

---

## 5. 커밋 이력

| 커밋 | 내용 |
|------|------|
| `d4a81fe` | feat(CF_Engine): train.py --output parquet / --from-parquet 옵션 구현 |

---

## 6. PR 현황

| 항목 | 내용 |
|------|------|
| PR 번호 | #25 |
| 상태 | OPEN |
| 제목 | feat(CF_Engine): train.py --output parquet / --from-parquet 옵션 구현 |
| URL | https://github.com/dhwang0803-glitch/dxshcool/pull/25 |

---

## 7. 보안 점검 결과

| 점검 항목 | 결과 |
|-----------|------|
| 하드코딩된 자격증명 | ✅ 없음 |
| os.getenv() 기본값 인프라 노출 | ✅ 없음 |
| .env 직접 읽기 | ✅ 없음 |
| .gitignore 확인 | ✅ `.env`, `*.parquet`, `data/` 모두 제외 |
| DB 접속 방식 | ✅ `src/data_loader.get_conn()` (os.getenv 방식) |

---

## 8. 현재 완료 상태

```
✅ src/data_loader.py
✅ src/als_model.py
✅ src/recommender.py
✅ scripts/train.py (--output parquet / --from-parquet 포함 전체 완성)
✅ scripts/export_to_db.py
✅ scripts/evaluate.py
✅ scripts/pilot_test.py
✅ config/als_config.yaml
✅ tests/ 9/9 PASSED
✅ PR #25 OPEN
```

**CF_Engine 핵심 구현 완료.**

---

## 9. 다음 세션 시작 방법

```
/init
```
