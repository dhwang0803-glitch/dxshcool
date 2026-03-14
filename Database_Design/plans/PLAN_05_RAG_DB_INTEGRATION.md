# Phase 5: RAG 연동 DB 설계 계획

**단계**: Phase 5 / 5
**목표**: RAG 파이프라인과 PostgreSQL의 연동 지점 설계 및 결측치 처리 후 DB 업데이트 전략
**선행 조건**: Phase 1~2 완료 (vod 테이블 존재), RAG 팀 병렬 진행 중

---

## 1. RAG 연동 개요

### 처리 대상 결측치 (설계요구사항.md 기준)

| 컬럼 | NULL 건수 | 비율 | 우선순위 | RAG 소스 |
|------|----------|------|---------|---------|
| director | 313건 | 0.19% | HIGH (필수) | IMDB / Wikipedia |
| smry | 28건 | 0.017% | MEDIUM (선택) | IMDB / Wikipedia |

### RAG 처리 추적 컬럼 (vod 테이블에 포함)

```sql
-- vod 테이블에 이미 포함된 RAG 추적 컬럼
rag_processed       BOOLEAN DEFAULT FALSE,    -- RAG 처리 완료 여부
rag_source          VARCHAR(64),              -- 'IMDB', 'Wikipedia', 'KMRB' 등
rag_processed_at    TIMESTAMPTZ               -- RAG 처리 시각
```

---

## 2. RAG → DB 업데이트 워크플로우

```
RAG 파이프라인 (별도 팀)
    │
    ├── 1. vod 테이블에서 NULL director/smry 조회
    │       SELECT full_asset_id, asset_nm, ct_cl
    │       FROM vod
    │       WHERE rag_processed = FALSE
    │         AND (director IS NULL OR smry IS NULL)
    │
    ├── 2. asset_nm으로 IMDB/Wikipedia API 검색
    │
    ├── 3. 검색 결과 → PostgreSQL UPDATE
    │       UPDATE vod SET
    │           director = '검색된 감독명',
    │           smry = '검색된 줄거리',
    │           rag_processed = TRUE,
    │           rag_source = 'IMDB',
    │           rag_processed_at = NOW()
    │       WHERE full_asset_id = '...'
    │
    └── 4. 처리 결과 로그 기록
```

---

## 3. RAG 처리 현황 조회 쿼리

### 처리 대기 목록 조회 (RAG 파이프라인 입력)
```sql
-- HIGH 우선순위: director NULL인 VOD
SELECT
    full_asset_id,
    asset_nm,
    ct_cl,
    genre,
    smry IS NULL AS smry_also_null
FROM vod
WHERE director IS NULL
  AND rag_processed = FALSE
ORDER BY ct_cl, asset_nm;

-- MEDIUM 우선순위: smry NULL인 VOD
SELECT
    full_asset_id,
    asset_nm,
    ct_cl,
    genre
FROM vod
WHERE smry IS NULL
  AND rag_processed = FALSE
  AND director IS NOT NULL   -- director 처리 완료 후 진행
ORDER BY ct_cl;
```

### RAG 처리 진행률 모니터링
```sql
SELECT
    rag_processed,
    rag_source,
    COUNT(*) AS count,
    MIN(rag_processed_at) AS first_processed,
    MAX(rag_processed_at) AS last_processed
FROM vod
WHERE director IS NOT NULL OR smry IS NOT NULL
GROUP BY rag_processed, rag_source
ORDER BY rag_processed DESC;
```

### 처리 완료율 대시보드
```sql
SELECT
    ROUND(100.0 * COUNT(*) FILTER (WHERE rag_processed = TRUE) / COUNT(*), 2)
        AS rag_completion_pct,
    COUNT(*) FILTER (WHERE director IS NULL) AS director_null_remaining,
    COUNT(*) FILTER (WHERE smry IS NULL) AS smry_null_remaining,
    COUNT(*) FILTER (WHERE rag_processed = TRUE) AS rag_completed,
    COUNT(*) AS total_vods
FROM vod;
```

---

## 4. RAG 업데이트 Python 함수 (참고용)

RAG 팀이 DB 업데이트 시 사용할 수 있는 함수 예시:

```python
def update_vod_after_rag(
    engine,
    full_asset_id: str,
    director: str | None = None,
    smry: str | None = None,
    rag_source: str = "IMDB"
) -> bool:
    """
    RAG 처리 완료 후 vod 테이블 업데이트

    Args:
        full_asset_id: VOD 식별자
        director: RAG로 찾은 감독명 (None이면 업데이트 안 함)
        smry: RAG로 찾은 줄거리 (None이면 업데이트 안 함)
        rag_source: RAG 소스 (IMDB / Wikipedia / KMRB)

    Returns:
        True: 업데이트 성공
        False: 업데이트 실패 또는 변경 없음
    """
    update_fields = {}
    if director is not None:
        update_fields['director'] = director
    if smry is not None:
        update_fields['smry'] = smry

    if not update_fields:
        return False

    update_fields.update({
        'rag_processed': True,
        'rag_source': rag_source,
        'rag_processed_at': 'NOW()'
    })

    # SQLAlchemy update
    with engine.connect() as conn:
        result = conn.execute(
            text("""
                UPDATE vod SET
                    director = COALESCE(:director, director),
                    smry = COALESCE(:smry, smry),
                    rag_processed = :rag_processed,
                    rag_source = :rag_source,
                    rag_processed_at = NOW()
                WHERE full_asset_id = :full_asset_id
            """),
            {
                'full_asset_id': full_asset_id,
                'director': director,
                'smry': smry,
                'rag_processed': True,
                'rag_source': rag_source
            }
        )
        conn.commit()

    return result.rowcount > 0
```

---

## 5. RAG 처리 배치 전략

### 일괄 처리 (권장)
```python
# 100건씩 배치 처리
SELECT full_asset_id, asset_nm
FROM vod
WHERE director IS NULL AND rag_processed = FALSE
LIMIT 100;

-- 처리 후 일괄 업데이트
UPDATE vod SET
    director = data.director,
    rag_processed = TRUE,
    rag_source = data.source,
    rag_processed_at = NOW()
FROM (VALUES
    ('asset_id_1', '감독A', 'IMDB'),
    ('asset_id_2', '감독B', 'Wikipedia'),
    ...
) AS data(full_asset_id, director, source)
WHERE vod.full_asset_id = data.full_asset_id;
```

### 처리 실패 시 재시도 전략
```sql
-- 처리 실패 레코드 (rag_processed=FALSE이지만 rag_processed_at이 있는 경우)
-- → 재시도 큐에 추가
SELECT full_asset_id, asset_nm
FROM vod
WHERE rag_processed = FALSE
  AND rag_processed_at IS NOT NULL  -- 시도했지만 실패
  AND rag_processed_at < NOW() - INTERVAL '1 day'  -- 1일 이상 경과
ORDER BY rag_processed_at;
```

---

## 6. RAG 연동 완료 후 확인사항

```sql
-- 최종 검증
SELECT
    COUNT(*) FILTER (WHERE director IS NULL) AS director_null,
    COUNT(*) FILTER (WHERE smry IS NULL) AS smry_null,
    COUNT(*) FILTER (WHERE rag_processed = TRUE) AS rag_done,
    COUNT(*) AS total
FROM vod;
-- 목표: director_null = 0 (RAG 예상 채워질 비율 95% 이상)
-- 목표: smry_null ≈ 6건 이하 (80% 채워질 경우)
```

---

## 7. 향후 확장: 임베딩 생성 연동

RAG 처리 완료 후 VOD_Embedding 파이프라인 트리거:

```
RAG 처리 완료 (rag_processed = TRUE)
    ↓
임베딩 생성 큐 (별도 큐 또는 이벤트)
    ↓
smry + asset_nm + genre_detail + director → 텍스트 임베딩 생성
    ↓
pgvector vod_embedding 테이블 적재 (VECTOR(512))
```

> **아키텍처 메모**: 벡터 저장소는 pgvector(PostgreSQL 내장) 단일화 결정.
> Milvus 미사용. 자세한 근거는 PLAN_04_EXTENSION_TABLES.md 참조.

---

**이전 단계**: PLAN_04_EXTENSION_TABLES.md
**전체 완료 후**: 논리 스키마를 실제 PostgreSQL DDL로 구현 시작 (PLAN_01 기준)
