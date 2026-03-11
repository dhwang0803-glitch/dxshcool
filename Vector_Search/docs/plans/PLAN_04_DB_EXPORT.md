# PLAN_04: 결과 DB 적재

**파일**: `scripts/export_to_db.py`
**입력**: 앙상블 TOP-N 결과
**출력**: DB `vod_similarity` 테이블 적재

---

## 목표

앙상블 검색 결과를 DB에 적재하여 `API_Server`가 직접 조회할 수 있도록 한다.

---

## 테이블 설계 (Database_Design 브랜치와 협의 필요)

```sql
CREATE TABLE IF NOT EXISTS vod_similarity (
    id              BIGSERIAL PRIMARY KEY,
    source_vod_id   VARCHAR(64) NOT NULL REFERENCES vod(full_asset_id),
    similar_vod_id  VARCHAR(64) NOT NULL REFERENCES vod(full_asset_id),
    final_score     REAL        NOT NULL,
    clip_score      REAL,
    content_score   REAL,
    alpha           REAL        NOT NULL DEFAULT 0.4,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vod_similarity UNIQUE (source_vod_id, similar_vod_id)
);

CREATE INDEX idx_vod_sim_source ON vod_similarity (source_vod_id);
```

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

다운스트림 `API_Server`의 `/similar/{asset_id}` 엔드포인트가 이 테이블을 조회한다.

```sql
SELECT similar_vod_id, final_score
FROM vod_similarity
WHERE source_vod_id = $1
ORDER BY final_score DESC
LIMIT 10;
```

---

**이전**: PLAN_03_ENSEMBLE.md
**완료 후**: API_Server 브랜치에 엔드포인트 구현 전달
