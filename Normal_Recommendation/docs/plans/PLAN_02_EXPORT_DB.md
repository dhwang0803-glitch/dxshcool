# PLAN_02: 추천 결과 DB 적재

**브랜치**: Normal_Recommendation
**스크립트**: `scripts/export_to_db.py`
**입력**: `data/popular_top20_by_genre_YYYYMMDD.parquet`
**출력**: `serving.popular_recommendation` 테이블

> **조장 전용**: DB 쓰기 권한 필요. 팀원은 PLAN_01에서 parquet 저장 후 조장에게 전달.

---

## 목표

parquet 파일을 읽어 `serving.popular_recommendation` 테이블에 적재.
기존 레코드 전체 DELETE 후 INSERT (전체 갱신 방식).

---

## 저장 테이블 스키마

```sql
serving.popular_recommendation
- popular_rec_id    SERIAL PK
- genre             VARCHAR
- rank              SMALLINT
- vod_id_fk         VARCHAR(64)
- score             REAL
- recommendation_type VARCHAR
- expires_at        TIMESTAMP
- UNIQUE (genre, rank)
```

---

## DB 적재 방식

### DELETE + INSERT 패턴

```sql
-- 전체 삭제 (장르 단위 관리 테이블)
DELETE FROM serving.popular_recommendation;

-- 신규 INSERT
INSERT INTO serving.popular_recommendation
    (genre, rank, vod_id_fk, score, recommendation_type, expires_at)
VALUES (%s, %s, %s, %s, %s, %s);
```

### expires_at (TTL)

```python
expires_at = datetime.now() + timedelta(days=7)  # 1주일 후 만료
```

1주일 1회 업데이트 방식이므로 expires_at = 현재시간 + 7일.

---

## 실행 방법

```bash
# parquet → DB 적재 (조장 전용)
python Normal_Recommendation/scripts/export_to_db.py \
    --from-parquet Normal_Recommendation/data/popular_top20_by_genre_20260319.parquet

# 드라이런
python Normal_Recommendation/scripts/export_to_db.py \
    --from-parquet Normal_Recommendation/data/popular_top20_by_genre_20260319.parquet \
    --dry-run
```

---

## 적재 완료 검증 쿼리

```sql
-- 장르별 건수 확인
SELECT genre, COUNT(*), MIN(score), MAX(score)
FROM serving.popular_recommendation
GROUP BY genre
ORDER BY genre;

-- 상위 5개 확인
SELECT genre, rank, vod_id_fk, score, expires_at
FROM serving.popular_recommendation
ORDER BY genre, rank
LIMIT 20;
```

---

## 예상 적재 건수

- 4개 장르 × Top-20 = **최대 80건**
- 같은 VOD가 여러 장르에 등장 가능 (UNIQUE가 genre+rank 기준이므로 문제없음)

---

**이전**: PLAN_01_POPULARITY.md
