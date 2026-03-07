# Phase 3 성능 테스트 결과

**실행일**: 2026-03-07
**환경**: PostgreSQL 15.4 (VPC Docker, 1core/4GB RAM)
**테스트 파일**: `Database_Design/tests/performance_test.sql`

---

## 테이블 크기

| 테이블 | 전체 크기 | 데이터 | 인덱스 |
|--------|----------|--------|--------|
| watch_history | 2,043 MB | 637 MB | 1,406 MB |
| vod | 141 MB | 82 MB | 60 MB |
| user | 60 MB | 34 MB | 26 MB |

---

## 1차 테스트 결과 (기본 설정)

| ID | 조회 패턴 | 목표 | 실제 | 판정 | 실행 계획 |
|----|----------|------|------|------|----------|
| P01 | 사용자별 시청이력 조회 | <100ms | 1,272ms | FAIL | idx_wh_user_id + Seq Scan(vod) |
| P02 | VOD별 시청 통계 조회 | <100ms | 15,920ms | FAIL | Bitmap Index Scan on idx_wh_vod_id (71,672 rows) |
| P03 | 날짜 범위 시청 조회(1주) | <500ms | 30,679ms | FAIL | Bitmap Index Scan on idx_wh_strt_dt (787,076 rows) |
| P04 | 만족도 상위 VOD 조회 | <500ms | 23,292ms | FAIL | Parallel Hash Join + external merge sort(disk) |
| P05 | 복합 인덱스 활용(사용자+날짜) | <100ms | **9ms** | **PASS** | Index Scan on idx_wh_user_id |
| P06 | 연령대별 선호 VOD(3-테이블 JOIN) | <500ms | 12,746ms | FAIL | Nested Loop + Parallel |

**1차 결과: 1/6 PASS (FAIL 5건)**

---

## FAIL 원인 분석

### P01 - 사용자별 시청이력 (1,272ms)
- `idx_wh_user_id`로 watch_history 조회는 정상 (Index Scan)
- JOIN 대상 vod 테이블(166K rows)을 **Seq Scan** 후 Hash Join
- shared read=10,488 블록 → 버퍼 캐시 미스 (cold cache)
- 개선: vod_pkey 캐시 워밍 또는 커버링 인덱스

### P02 - VOD별 시청 통계 (15,920ms)
- 테스트 대상 VOD가 **최다 시청 VOD (71,672건)**
- Bitmap Heap Scan으로 27,446개 heap block 접근 → IO 병목
- 극단적 케이스 (일반 VOD는 수십~수백건)
- 개선: 중간 규모 VOD로 재테스트 시 목표 달성 가능

### P03 - 날짜 범위 1주 (30,679ms)
- 1주(2023-01-01~07) = **787,076건 = 전체 19.7%**
- 인덱스 사용 후에도 787K 행 집계 → 근본적으로 데이터 볼륨 문제
- 개선: 파티셔닝(연/월 단위) 또는 일별 집계 materialized view

### P04 - 만족도 상위 VOD (23,292ms)
- 전체 테이블 스캔 불가피 (satisfaction > 0 = 2.98M건)
- **external merge sort (Disk)** 발생 → work_mem 부족
- 개선: `work_mem = '256MB'` 설정 또는 부분 인덱스

### P05 - 복합 인덱스 (9ms) ✓
- `idx_wh_user_id` Index Scan → 9ms로 목표 달성
- `idx_wh_user_strt` 복합 인덱스 대신 단순 인덱스 선택 (플래너 판단)

### P06 - 연령대별 VOD (12,746ms)
- 30대 사용자 15,593명 → watch_history Nested Loop 138,380회
- `idx_user_age_grp` 정상 사용, idx_wh_user_id 정상 사용
- IO 볼륨 자체가 큼 (shared read=35,487)
- 개선: work_mem 증가 + 결과 캐싱(Redis) 전략

---

## 설정별 전체 비교 (Cold Cache 기준)

| ID | 기본(128MB/4MB) | work_mem=256MB | 1GB/16MB | 1GB/256MB | 1GB/32MB/2workers | **1GB/32MB/0workers** |
|----|----------------|----------------|---------|----------|-------------------|----------------------|
| P01 | 1,272ms | 979ms | 1,006ms | 937ms | 1,067ms | 1,051ms |
| P02 | 15,920ms | 9,559ms | 21,404ms | 18,311ms | 17,403ms | 24,565ms |
| P03 | 30,679ms | - | 30,996ms | 43,935ms | 28,804ms | 26,611ms |
| P04 | 23,292ms | **15,703ms** | 87,565ms | 54,205ms | 50,340ms | 41,336ms |
| P05 | **9ms** | - | 11ms | 45ms | 33ms | 18ms |
| P06 | 12,746ms | - | 23,866ms | 21,863ms | 13,940ms | 21,120ms |

## Warm Cache 결과 (1GB/32MB/2workers 설정, 2차 실행)

| ID | Cold | Warm | Cache 상태 | 변화 |
|----|------|------|-----------|------|
| P01 | 1,067ms | 3,049ms | hit=10,597 (100%) | 악화 (1코어 CPU 경합) |
| P02 | 17,403ms | **7,004ms** | hit=27,509 (100%) | -60% |
| P03 | 28,804ms | **25,894ms** | hit=57,112 (100%) | -10% |
| P04 | 50,340ms | 60,377ms | hit=68,926+read=22,997 | 악화 (637MB 미완충) |
| P05 | 33ms | **15ms** | hit=155 (100%) | -55% |
| P06 | 13,940ms | 17,611ms | hit=254,447 (100%) | 악화 (1코어 CPU 경합) |

## Warm Cache 결과 (1GB/32MB/0workers 설정, 2차 실행)

| ID | Cold | Warm | Cache 상태 | 변화 |
|----|------|------|-----------|------|
| P01 | 1,051ms | 4,262ms | hit=10,597 (100%) | 악화 — vod Seq Scan 4,067ms (CPU 처리 병목) |
| P02 | 24,565ms | **1,714ms** | hit=27,509 (100%) | **-93%** |
| P03 | 26,611ms | **17,984ms** | hit=57,112 (100%) | **-32%** |
| P04 | 41,336ms | **19,532ms** | hit=66,747+read=25,176 | **-53%** (부분 캐시) |
| P05 | 18ms | **11ms** | hit=155 (100%) | **-39%** |
| P06 | 21,120ms | 31,288ms | hit=180,396+read=25,144 | 악화 — disk read 잔류 |

## 전체 테스트 최고 기록

| ID | 최고 기록 | 설정 | 판정 |
|----|---------|------|------|
| P01 | 937ms | 1GB/256MB cold | FAIL |
| P02 | **1,714ms** | **1GB/32MB/0workers warm** | FAIL |
| P03 | **17,984ms** | **1GB/32MB/0workers warm** | FAIL |
| P04 | 15,703ms | 128MB/256MB cold | FAIL |
| **P05** | **9ms** | 기본 설정 | **PASS** |
| P06 | 12,746ms | 기본 설정 | FAIL |

---

## 최적화 권고사항

### 즉시 적용 가능
```sql
-- 세션 단위 work_mem 증가 (P04 disk sort 해소)
SET work_mem = '256MB';

-- 부분 인덱스 추가 (satisfaction > 0 필터 최적화)
CREATE INDEX CONCURRENTLY idx_wh_satisfaction_nonzero
    ON watch_history (satisfaction)
    WHERE satisfaction > 0;

-- 커버링 인덱스 (P01 vod JOIN 최적화)
CREATE INDEX CONCURRENTLY idx_wh_user_covering
    ON watch_history (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);
```

### 중장기 적용
```sql
-- P03 근본 해결: strt_dt 기준 파티셔닝
CREATE TABLE watch_history_2023_01
    PARTITION OF watch_history
    FOR VALUES FROM ('2023-01-01') TO ('2023-02-01');

-- P02/P06: 집계 결과 Materialized View
CREATE MATERIALIZED VIEW mv_vod_stats AS
SELECT vod_id_fk, COUNT(*) AS views, AVG(satisfaction) AS avg_sat
FROM watch_history GROUP BY vod_id_fk;
```

### VPC 환경 한계
- 1코어/4GB RAM 환경에서 대용량 집계 쿼리는 구조적 한계 존재
- 추천/임베딩 계산은 로컬에서 처리 후 결과만 VPC DB에 저장하는 현재 아키텍처가 최선
