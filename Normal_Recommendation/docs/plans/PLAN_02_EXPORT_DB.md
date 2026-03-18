# PLAN_02: 추천 결과 DB 적재

**브랜치**: Normal_Recommendation
**스크립트**: `scripts/export_to_db.py`
**입력**: `data/recommendations_popular_YYYYMMDD.parquet`
**출력**: `serving.vod_recommendation` 테이블

> **조장 전용**: DB 쓰기 권한 필요. 팀원은 PLAN_01에서 parquet 저장 후 조장에게 전달.

---

## 목표

parquet 파일을 읽어 `serving.vod_recommendation` 테이블에 적재.
기존 `'POPULAR'` 타입 레코드를 DELETE 후 INSERT (전체 갱신 방식).

---

## DB 적재 방식

### DELETE + INSERT 패턴

```sql
-- 기존 POPULAR 추천 결과 전체 삭제
DELETE FROM serving.vod_recommendation
WHERE recommendation_type = 'POPULAR';

-- 신규 추천 결과 INSERT
INSERT INTO serving.vod_recommendation
    (vod_id_fk, rank, score, recommendation_type, user_id_fk, source_vod_id)
VALUES
    (%s, %s, %s, 'POPULAR', NULL, NULL);
```

### 이유
- `serving.vod_recommendation` UNIQUE (user_id_fk, vod_id_fk)
- user_id_fk=NULL 이므로 동일 vod가 여러 장르에 등장 가능 → 장르/ct_cl 컬럼 기준 중복 제거 후 적재
- POPULAR 타입만 삭제하므로 COLLABORATIVE/CONTENT_BASED 타입에 영향 없음

---

## 적재 전 중복 제거

같은 VOD가 여러 장르에 Top-N으로 선정될 수 있음.
`serving.vod_recommendation`은 `(user_id_fk, vod_id_fk)` UNIQUE이므로,
user_id_fk=NULL인 POPULAR 레코드는 vod_id_fk 기준으로 중복 제거 필요.

```python
# parquet 로드 후 vod_id_fk 기준 최고 score 유지
df = df.sort_values('score', ascending=False).drop_duplicates('vod_id_fk')
```

---

## 적재 컬럼 매핑

| serving.vod_recommendation | parquet 컬럼 | 값 |
|---------------------------|-------------|-----|
| `vod_id_fk` | `vod_id_fk` | VOD ID |
| `rank` | `rank` | 인기 순위 |
| `score` | `score` | 인기 점수 |
| `recommendation_type` | 고정 | `'POPULAR'` |
| `user_id_fk` | 고정 | `NULL` |
| `source_vod_id` | 고정 | `NULL` |

---

## 실행 방법

```bash
conda activate myenv

# parquet → DB 적재 (조장 전용)
python scripts/export_to_db.py --from-parquet data/recommendations_popular_20260317.parquet

# 드라이런 (DB 저장 없이 적재 예정 건수만 출력)
python scripts/export_to_db.py --from-parquet data/recommendations_popular_20260317.parquet --dry-run
```

---

## 적재 완료 검증 쿼리

```sql
-- POPULAR 추천 결과 건수 확인
SELECT COUNT(*), MIN(score), MAX(score), AVG(score)
FROM serving.vod_recommendation
WHERE recommendation_type = 'POPULAR';

-- 상위 10개 확인
SELECT vod_id_fk, rank, score
FROM serving.vod_recommendation
WHERE recommendation_type = 'POPULAR'
ORDER BY score DESC
LIMIT 10;
```

---

## 예상 적재 건수

- 장르 수: 약 20~30개 × top_n(20) = 최대 600건
- ct_cl 수: 약 10개 × top_n(20) = 최대 200건
- 중복 제거 후 실제 적재: **약 200~500건** 예상

---

**이전**: PLAN_01_POPULARITY.md
