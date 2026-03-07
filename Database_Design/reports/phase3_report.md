# Phase 3 결과 보고서

**Phase**: Phase 3 → Phase 3B - 성능 검증 + 성능 개선
**작성일**: 2026-03-07
**상태**: Phase 3B 진행 중 (P01/P05 PASS, P04/P06 → OPT-2 MV로 해결 예정, P02/P03 → OPT-3 파티셔닝 대기)

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
| watch_history | 2,683 MB | 637 MB | 2,047 MB (OPT-1 인덱스 추가 후) |
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

### VPC PostgreSQL 설정 이력

| 설정 | shared_buffers | work_mem | 비고 |
|------|---------------|----------|------|
| 초기 | 128MB | 4MB | PostgreSQL 기본값 |
| 2차 | 128MB | 256MB | 세션 단위 적용 |
| 3차 | 1GB | 16MB | shared_buffers 증설 |
| 4차 | 1GB | 256MB | 두 설정 동시 적용 |
| 5차 | 1GB | 32MB | + maintenance_work_mem=256MB, max_parallel_workers_per_gather=2 |
| 6차 | 1GB | 32MB | + max_parallel_workers_per_gather=0 |
| 7차 | 1GB | 32MB | + random_page_cost=1.0 (P02/P03 역효과로 기각) |
| **최종** | **1GB** | **32MB** | **+ max_parallel_workers_per_gather=0, random_page_cost=1.5** |

### 1차 테스트 상세 결과 (기본 설정)

| ID | 조회 패턴 | 목표 | 실제 | 판정 | 주요 플랜 |
|----|----------|------|------|------|----------|
| P01 | 사용자별 시청이력 + VOD JOIN | <100ms | 1,272ms | FAIL | Index Scan(wh) + Seq Scan(vod) + Hash Join |
| P02 | VOD별 시청 통계 (최다 시청 VOD) | <100ms | 15,920ms | FAIL | Bitmap Index Scan (71,672 rows) |
| P03 | 날짜 범위 1주 집계 | <500ms | 30,679ms | FAIL | Bitmap Index Scan (787,076 rows = 19.7%) |
| P04 | 만족도 상위 VOD (전체 집계) | <500ms | 23,292ms | FAIL | Parallel Hash Join + external merge Disk |
| **P05** | **복합 인덱스 (사용자+날짜)** | **<100ms** | **9ms** | **PASS** | Index Scan on idx_wh_user_id |
| P06 | 연령대별 VOD (3-테이블 JOIN) | <500ms | 12,746ms | FAIL | Nested Loop + Parallel (138,380 loops) |

### 설정별 전체 비교 (Cold Cache)

| ID | 기본(128/4MB) | work_mem=256MB | 1GB/16MB | 1GB/256MB | 1GB/32MB/2w | **1GB/32MB/0w** |
|----|--------------|----------------|---------|----------|-------------|-----------------|
| P01 | 1,272ms | 979ms | 1,006ms | 937ms | 1,067ms | 1,051ms |
| P02 | 15,920ms | 9,559ms | 21,404ms | 18,311ms | 17,403ms | 24,565ms |
| P03 | 30,679ms | - | 30,996ms | 43,935ms | 28,804ms | 26,611ms |
| P04 | 23,292ms | **15,703ms** | 87,565ms | 54,205ms | 50,340ms | 41,336ms |
| P05 | **9ms** | - | 11ms | 45ms | 33ms | 18ms |
| P06 | 12,746ms | - | 23,866ms | 21,863ms | 13,940ms | 21,120ms |

### Warm Cache 결과 (1GB/32MB/2workers, 2차 실행)

| ID | Cold | Warm | Cache 상태 | 변화 |
|----|------|------|-----------|------|
| P01 | 1,067ms | 3,049ms | shared hit=10,597 (100%) | 악화 — 1코어 CPU 경합 |
| P02 | 17,403ms | **7,004ms** | shared hit=27,509 (100%) | **-60%** |
| P03 | 28,804ms | **25,894ms** | shared hit=57,112 (100%) | **-10%** |
| P04 | 50,340ms | 60,377ms | hit=68,926+read=22,997 | 악화 — 637MB 미완충 |
| P05 | 33ms | **15ms** | shared hit=155 (100%) | **-55%** |
| P06 | 13,940ms | 17,611ms | shared hit=254,447 (100%) | 악화 — 1코어 CPU 경합 |

### Warm Cache 결과 (1GB/32MB/0workers, 2차 실행)

| ID | Cold | Warm | Cache 상태 | 변화 |
|----|------|------|-----------|------|
| P01 | 1,051ms | 4,262ms | shared hit=10,597 (100%) | 악화 — vod Seq Scan CPU 처리 병목 |
| P02 | 24,565ms | **1,714ms** | shared hit=27,509 (100%) | **-93%** |
| P03 | 26,611ms | **17,984ms** | shared hit=57,112 (100%) | **-32%** |
| P04 | 41,336ms | **19,532ms** | hit=66,747+read=25,176 | **-53%** (부분 캐시) |
| P05 | 18ms | **11ms** | shared hit=155 (100%) | **-39%** |
| P06 | 21,120ms | 31,288ms | hit=180,396+read=25,144 | 악화 — disk read 잔류 |

---

## 3. 오류 원인 분석

### Warm Cache 역설 분석

**2workers 설정 (P01, P04, P06 악화)**
- **원인**: max_parallel_workers_per_gather=2로 병렬 워커 2개가 VPC 1코어를 경합
- **P04**: watch_history 637MB가 1GB shared_buffers에 완전히 안 들어감 → 22K blocks disk read 잔류
- **결론**: 1코어 환경에서 병렬 처리는 오히려 역효과

**0workers 설정 결과 (max_parallel_workers_per_gather=0)**
- **P02 warm -93%**: 24,565ms → 1,714ms. 병렬 없이 단순 Bitmap Heap Scan + GroupAggregate, 완전 캐시 효과 극대화
- **P04 warm -53%**: 41,336ms → 19,532ms. HashAggregate(Batches:1 in-memory) + Hash Join, 부분 disk read(25K blocks) 잔류
- **P01 warm 악화**: 1,051ms → 4,262ms. vod(166K rows) Seq Scan이 warm에서 4,067ms → 1코어 CPU 순차 처리 병목. 커버링 인덱스로 해결 가능
- **P06 warm 악화**: 21,120ms → 31,288ms. watch_history Seq Scan 22,532ms + disk read 25,144 blocks 잔류. 데이터 볼륨 한계

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
-- 1. 1코어 환경 병렬 처리 비활성화 검토 (postgresql.conf)
-- max_parallel_workers_per_gather = 0
-- warm cache 역설(P01/P06 오히려 느려짐) 해소 가능

-- 2. 부분 인덱스: satisfaction > 0 필터 최적화
CREATE INDEX CONCURRENTLY idx_wh_satisfaction_nonzero
    ON watch_history (satisfaction DESC)
    WHERE satisfaction > 0;

-- 3. 커버링 인덱스: P01 vod Seq Scan 제거
CREATE INDEX CONCURRENTLY idx_wh_user_covering
    ON watch_history (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);
```

### 최종 권장 VPC 설정

```
shared_buffers = 1GB                    # 적용됨
work_mem = 32MB                         # 적용됨
maintenance_work_mem = 256MB            # 적용됨
max_parallel_workers_per_gather = 0     # 1코어 환경 병렬 비활성화 (적용됨)
random_page_cost = 1.5                  # 적용됨 (warm cache 환경 반영)
```

**0workers 적용 효과**: P02 warm -93%(1,714ms), P03 warm -32%(17,984ms), P04 warm -53%(19,532ms).
**random_page_cost=1.5 추가 효과**: P01 cold 1,051ms → **128ms(-88%)**, warm **28ms(PASS)**. P06 warm 31,288ms → **10,355ms(-67%)**.

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

### Phase 3 적용된 최적화

- `performance_test.sql`: `SET statement_timeout = '120s'` 추가 (무한 대기 방지)
- `performance_test.sql`: ANALYZE 전처리 제거 (VPC 1코어에서 50분 이상 소요)
- `work_mem = '256MB'` 세션 단위 적용 → P04 disk sort 제거 확인

### Phase 3B OPT-1 적용된 최적화

| 항목 | 내용 | 효과 |
|------|------|------|
| `idx_wh_user_covering` (576MB) | (user_id_fk, strt_dt DESC) INCLUDE (vod_id_fk, completion_rate, satisfaction) | P01 플래너 Nested Loop 전환 조건 제공 |
| `idx_wh_satisfaction_nonzero` (64MB) | (satisfaction DESC) WHERE satisfaction > 0 | P04 부분 스캔 지원 (MV 적용 전 보조) |
| `ANALYZE watch_history` | 통계 갱신 | P02 플랜 개선 (490ms 달성) |
| `random_page_cost=1.5` | 플래너 랜덤 I/O 비용 조정 | P01 Nested Loop+Memoize 채택 → **28ms warm PASS** |

### 미적용 최적화 (OPT-2, OPT-3 진행 예정)

- Materialized View (`mv_vod_satisfaction_stats`, `mv_age_grp_vod_stats`): P04/P06 → <10ms 예상
- 파티셔닝: P03 근본 해결, 데이터 재적재 필요 (팀 협의 후 결정)

---

## 6. 성능 목표 재설정 권고

현재 성능 목표는 충분한 RAM을 갖춘 서버 기준으로 설정되어 있음. VPC(1core/4GB) 환경에서 현실적인 목표치 재설정을 권고함.

| 조회 패턴 | 기존 목표 | Phase 3B 현재 | 달성 방법 | 상태 |
|----------|----------|--------------|----------|------|
| 사용자별 시청이력 | <100ms | **28ms warm** | random_page_cost=1.5 + Nested Loop | **✅ PASS** |
| VOD별 통계 (최다시청) | <100ms | 3,203ms warm | 구조적 한계 (71K rows) | ❌ |
| 날짜 범위 (1주) | <500ms | 15,315ms warm | OPT-3 파티셔닝 후 개선 | ❌ |
| 만족도 집계 | <500ms | 22,201ms cold | OPT-2 MV로 대체 예정 | ❌ |
| 복합 인덱스 조회 | <100ms | **9~28ms** | 현행 유지 | **✅ PASS** |
| 연령대별 집계 | <500ms | 10,355ms warm | OPT-2 MV로 대체 예정 | ❌ |

---

## 7. 다음 Phase 권고사항

- **Phase 3B 진행 중**: OPT-1 완료(P01 PASS), OPT-2(MV) → OPT-3(파티셔닝) 순서로 진행
- **OPT-2 다음 단계**: `mv_vod_satisfaction_stats`, `mv_age_grp_vod_stats` 생성 → P04/P06 <10ms 목표
- **추천 시스템 아키텍처**: 집계 결과는 VPC가 아닌 로컬에서 계산 후 결과만 DB에 저장하는 현행 방향 유지
- **Phase 4 참조 파일**: `Database_Design/plans/PLAN_04_EXTENSION_TABLES.md`
- **Phase 3B 참조 파일**: `Database_Design/plans/PLAN_03B_PERFORMANCE_OPT.md`
