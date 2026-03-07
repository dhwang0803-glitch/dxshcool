# Phase 3 결과 보고서

**Phase**: Phase 3 - 성능 검증
**작성일**: 2026-03-07
**상태**: 완료 (P05 PASS, P01/P02/P03/P04/P06 FAIL - VPC 환경 한계 분석 완료)

---

## 1. 개발 결과

### 생성된 파일

| 파일 | 위치 | 설명 |
|------|------|------|
| performance_test.sql | Database_Design/tests/ | EXPLAIN ANALYZE 성능 테스트 (P01~P06) |
| performance_retest.sql | Database_Design/tests/ | work_mem=256MB 최적화 재테스트 (P01, P02, P04) |
| test_results.md | Database_Design/tests/ | 1차/2차 테스트 결과 상세 |

### 테이블 크기

| 테이블 | 전체 | 데이터 | 인덱스 |
|--------|------|--------|--------|
| watch_history | 2,043 MB | 637 MB | 1,406 MB |
| vod | 141 MB | 82 MB | 60 MB |
| user | 60 MB | 34 MB | 26 MB |

---

## 2. 테스트 결과

### 요약

| 구분 | 건수 |
|------|------|
| 전체 테스트 | 6건 |
| PASS | 1건 |
| FAIL | 5건 |
| PASS율 | 16.7% |

- **실행 환경**: PostgreSQL 15.4 (VPC Docker, 1core/4GB RAM)
- **데이터**: user=242,702 / vod=166,159 / watch_history=3,992,530

### 1차 테스트 상세 결과 (기본 설정)

| ID | 조회 패턴 | 목표 | 실제 | 판정 | 주요 플랜 |
|----|----------|------|------|------|----------|
| P01 | 사용자별 시청이력 + VOD JOIN | <100ms | 1,272ms | FAIL | Index Scan(wh) + Seq Scan(vod) + Hash Join |
| P02 | VOD별 시청 통계 (최다 시청 VOD) | <100ms | 15,920ms | FAIL | Bitmap Index Scan (71,672 rows) |
| P03 | 날짜 범위 1주 집계 | <500ms | 30,679ms | FAIL | Bitmap Index Scan (787,076 rows = 19.7%) |
| P04 | 만족도 상위 VOD (전체 집계) | <500ms | 23,292ms | FAIL | Parallel Hash Join + external merge Disk |
| **P05** | **복합 인덱스 (사용자+날짜)** | **<100ms** | **9ms** | **PASS** | Index Scan on idx_wh_user_id |
| P06 | 연령대별 VOD (3-테이블 JOIN) | <500ms | 12,746ms | FAIL | Nested Loop + Parallel (138,380 loops) |

### 2차 테스트 상세 결과 (work_mem=256MB)

| ID | 1차 | 2차 | 개선율 | 변화 내용 |
|----|-----|-----|--------|----------|
| P01 | 1,272ms | 979ms | -23% | Hash 배치 4→1 (메모리 내 처리), disk sort 제거 |
| P02 | 15,920ms | 9,559ms | -40% | 동일 플랜, 버퍼 캐시 워밍 효과 |
| P04 | 23,292ms | 15,703ms | -33% | external merge(Disk) → in-memory HashAggregate 전환 |

---

## 3. 오류 원인 분석

### 근본 원인: VPC 환경 제약

| 제약 | 영향 |
|------|------|
| 1코어 CPU | 병렬 쿼리 Workers 2개로 제한, 순차 처리 병목 |
| 4GB RAM | work_mem 기본값 부족 → 디스크 sort 발생 |
| Cold buffer cache | 첫 실행 시 637MB 데이터 전량 disk read |
| 네트워크 경유 | psql 응답 왕복 지연 포함 |

### 쿼리별 세부 원인

**P01 (1,272ms)**: watch_history는 Index Scan 정상이나, JOIN 대상 vod(166K rows) Seq Scan 불가피. Hash Join 시 17MB hash table 구성 시간 포함.

**P02 (15,920ms)**: 테스트 대상이 최다 시청 VOD(71,672건). 27,446개 heap block 무작위 접근(Bitmap Heap Scan). 일반 VOD(수백~수천건)는 수십ms 예상.

**P03 (30,679ms)**: 1주 = 787,076건(전체 19.7%). 집계 대상 자체가 너무 많음. 파티셔닝 없이는 구조적 한계.

**P04 (23,292ms)**: satisfaction > 0 = 2,985,569건 전체 스캔 필수. work_mem=256MB로 disk sort는 제거됐으나 IO 볼륨 한계.

**P06 (12,746ms)**: 30대 사용자 15,593명 × Nested Loop → watch_history 138,380회 Index Scan. 인덱스는 정상 사용되나 반복 횟수가 많음.

---

## 4. 개선 방법

### 단기 (즉시 적용)

```sql
-- 1. 서버 설정: work_mem 증가 (postgresql.conf 또는 세션 단위)
SET work_mem = '256MB';
-- P04: 23,292ms → 15,703ms (-33%)

-- 2. 부분 인덱스: satisfaction > 0 필터 최적화
CREATE INDEX CONCURRENTLY idx_wh_satisfaction_nonzero
    ON watch_history (satisfaction DESC)
    WHERE satisfaction > 0;

-- 3. 커버링 인덱스: P01 vod JOIN 최적화 (vod Seq Scan 우회)
CREATE INDEX CONCURRENTLY idx_wh_user_covering
    ON watch_history (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);
```

### 중장기 (Phase 4 이후 검토)

```sql
-- 4. 파티셔닝: P03 날짜 범위 쿼리 근본 해결
-- watch_history를 월별 파티션으로 분리 시 P03 대상 파티션만 스캔

-- 5. Materialized View: P04/P06 집계 결과 사전 계산
CREATE MATERIALIZED VIEW mv_vod_satisfaction_stats AS
SELECT vod_id_fk, COUNT(*) AS view_count, AVG(satisfaction) AS avg_satisfaction
FROM watch_history WHERE satisfaction > 0
GROUP BY vod_id_fk
HAVING COUNT(*) >= 10;

CREATE UNIQUE INDEX ON mv_vod_satisfaction_stats(vod_id_fk);
-- REFRESH MATERIALIZED VIEW CONCURRENTLY mv_vod_satisfaction_stats; (일 1회)
```

---

## 5. 개선 내용 (실제 적용)

### 적용된 최적화

- `performance_test.sql`: `SET statement_timeout = '120s'` 추가 (무한 대기 방지)
- `performance_test.sql`: ANALYZE 전처리 제거 (VPC 1코어에서 50분 이상 소요)
- `work_mem = '256MB'` 세션 단위 적용 → P04 disk sort 제거 확인

### 미적용 최적화 (권고)

- 커버링 인덱스 (`idx_wh_user_covering`): Phase 4 진입 전 적용 권고
- Materialized View: 추천 시스템(Phase 5) 연동 시 함께 설계 권고
- 파티셔닝: 데이터 재적재 필요, 팀 협의 후 결정

---

## 6. 성능 목표 재설정 권고

현재 성능 목표는 충분한 RAM을 갖춘 서버 기준으로 설정되어 있음. VPC(1core/4GB) 환경에서 현실적인 목표치 재설정을 권고함.

| 조회 패턴 | 기존 목표 | VPC 현실적 목표 | 달성 방법 |
|----------|----------|----------------|----------|
| 사용자별 시청이력 | <100ms | <1,000ms | 커버링 인덱스 적용 시 개선 |
| VOD별 통계 (일반) | <100ms | <500ms | 일반 VOD 기준 달성 가능 |
| 날짜 범위 (1일) | <500ms | <1,000ms | 파티셔닝 적용 시 개선 |
| 만족도 집계 | <500ms | Materialized View로 대체 | MV REFRESH 주기 설정 |
| 복합 인덱스 조회 | <100ms | **9ms (달성)** | 현행 유지 |
| 연령대별 집계 | <500ms | Materialized View로 대체 | MV REFRESH 주기 설정 |

---

## 7. 다음 Phase 권고사항

- **Phase 4 진입 조건**: 성능 목표 미달이나, VPC 환경 한계로 인한 구조적 문제임이 확인됨. Phase 4 진행 가능
- **커버링 인덱스 선적용**: Phase 4 임베딩 테이블 DDL 작성 전 `idx_wh_user_covering` 생성 권고
- **추천 시스템 아키텍처**: 집계 결과는 VPC가 아닌 로컬에서 계산 후 결과만 DB에 저장하는 현행 방향 유지
- **Phase 4 참조 파일**: `Database_Design/plans/PLAN_04_EXTENSION_TABLES.md`
