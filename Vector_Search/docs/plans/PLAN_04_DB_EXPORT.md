# PLAN_04: 결과 DB 적재

**파일**: `scripts/export_to_db.py`
**입력**: 앙상블 TOP-N 결과
**출력**: `serving.vod_recommendation` 테이블 적재

---

## 목표

앙상블 검색 결과를 `serving.vod_recommendation`에 적재하여 `API_Server`가 직접 조회할 수 있도록 한다.

---

## 테이블 (Database_Design 브랜치 확정 스키마)

`serving.vod_recommendation` — Gold/Serving 계층 테이블 (신규 생성 불필요, 이미 존재)

```
source_vod_id       VARCHAR(64)   기준 VOD ID (콘텐츠 기반, user_id_fk=NULL)
user_id_fk          VARCHAR(64)   사용자 ID (유저 기반 추천 시, 현재는 NULL)
vod_id_fk           VARCHAR(64)   추천 VOD ID
rank                SMALLINT      추천 순위
score               REAL          코사인 유사도 (0~1)
recommendation_type VARCHAR(32)   'CONTENT_BASED' 고정
expires_at          TIMESTAMPTZ   TTL 7일 자동 설정
```

- CHECK 제약: `user_id_fk` 또는 `source_vod_id` 중 하나는 필수
- UNIQUE 인덱스: `(source_vod_id, vod_id_fk) WHERE source_vod_id IS NOT NULL`
- TTL: 7일 후 db_maintenance.py가 자동 삭제

---

## 실행 방법

```bash
# 전체 vod 기준 유사도 계산 후 적재
python scripts/export_to_db.py

# 특정 vod_id만 적재
python scripts/export_to_db.py --vod-id <full_asset_id>

# 드라이런 (DB INSERT 없이 결과만 출력)
python scripts/export_to_db.py --dry-run --limit 10
```

---

## API_Server 연동

`API_Server`의 `/similar/{asset_id}` 엔드포인트가 이 테이블을 조회한다.

```sql
SELECT vod_id_fk, score
FROM serving.vod_recommendation
WHERE source_vod_id = $1
  AND recommendation_type = 'CONTENT_BASED'
  AND expires_at > NOW()
ORDER BY rank
LIMIT 10;
```

---

**이전**: PLAN_03_ENSEMBLE.md
**완료 후**: API_Server 브랜치에 엔드포인트 구현 전달
