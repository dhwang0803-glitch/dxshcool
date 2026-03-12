-- =============================================================
-- Phase 3C OPT-3: watch_history 주별 파티셔닝 마이그레이션
-- 파일: Database_Design/schema/partition_watch_history.sql
-- 작성일: 2026-03-08
-- 참조: PLAN_03C_PARTITIONING_ANALYSIS.md
-- =============================================================
-- 목적: watch_history(3.99M rows, 637MB)를 strt_dt 기준 주별 파티션 테이블로 전환
--       P03 날짜 범위 조회 cold 32,705ms → ~5,000ms, warm 15,315ms → ~1,500ms 목표
--
-- 실행 순서: 아래 STEP 순서대로 실행. 각 STEP 완료 후 다음 진행.
-- 예상 소요시간: 총 2~3시간 (심야 배치 권장)
--   - Step 1~3: 5분
--   - Step 4 (데이터 복사): 30~60분
--   - Step 5~6 (인덱스 생성): 60~120분
--   - Step 7~8 (검증 + 스왑): 5분
--
-- 파티션 경계: 매주 일요일 시작 (7일 단위)
--   watch_history_20230101: [2023-01-01, 2023-01-08)  ← P03 테스트 쿼리 범위
--   watch_history_20230108: [2023-01-08, 2023-01-15)
--   watch_history_20230115: [2023-01-15, 2023-01-22)
--   watch_history_20230122: [2023-01-22, 2023-01-29)
--   watch_history_20230129: [2023-01-29, 2023-02-05)
--   watch_history_default:  위 범위에 해당 없는 데이터 (안전망)
--
-- 주의사항:
--   1. 파티션 테이블의 PK는 파티션 키(strt_dt)를 포함해야 함 (PostgreSQL 제약)
--      → PRIMARY KEY 변경: (watch_history_id) → (watch_history_id, strt_dt)
--      → watch_history_id는 IDENTITY 유지, 다른 테이블의 FK 참조 없으므로 영향 없음
--   2. 외래키(user_id_fk, vod_id_fk)는 Step 5에서 추가 (복사 속도 향상 목적)
--   3. 테이블 스왑은 트랜잭션 내에서 원자적으로 실행 → 서비스 중단 최소화
--   4. 구 테이블(watch_history_old)은 검증 완료 후 수동 삭제
-- =============================================================


-- =============================================================
-- [STEP 0] 사전 확인 (실행 후 결과 확인 필수)
-- =============================================================

-- 현재 테이블 크기 확인
SELECT
    relname                                              AS table_name,
    pg_size_pretty(pg_total_relation_size(relid))        AS total_size,
    pg_size_pretty(pg_relation_size(relid))              AS data_size,
    pg_size_pretty(pg_total_relation_size(relid)
                   - pg_relation_size(relid))            AS index_size
FROM pg_catalog.pg_statio_user_tables
WHERE relname = 'watch_history';

-- 디스크 여유 공간 확인 (최소 2GB 필요: 복사본 + 인덱스)
-- psql 클라이언트에서 실행: \! df -h /var/lib/postgresql

-- 현재 행 수 확인
SELECT COUNT(*) AS current_rows FROM watch_history;
-- 기대값: 3,992,530


-- =============================================================
-- [STEP 1] 새 파티션 테이블 생성
-- 예상 소요: 1초
-- =============================================================

CREATE TABLE watch_history_new (
    -- PRIMARY KEY에 strt_dt 포함 (파티션 테이블 필수 제약)
    watch_history_id    BIGINT          GENERATED ALWAYS AS IDENTITY,
    user_id_fk          VARCHAR(64)     NOT NULL,
    vod_id_fk           VARCHAR(64)     NOT NULL,
    strt_dt             TIMESTAMPTZ     NOT NULL,
    use_tms             REAL            NOT NULL,
    completion_rate     REAL,
    satisfaction        REAL,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),

    -- PK: (watch_history_id, strt_dt) — strt_dt 포함 필수
    CONSTRAINT pk_wh_new PRIMARY KEY (watch_history_id, strt_dt),

    -- 중복 방지: 동일 사용자-VOD-시각 복수 기록 방지
    CONSTRAINT uq_wh_user_vod_strt_new UNIQUE (user_id_fk, vod_id_fk, strt_dt),

    -- CHECK 제약
    CONSTRAINT chk_wh_use_tms_new          CHECK (use_tms >= 0),
    CONSTRAINT chk_wh_completion_rate_new  CHECK (completion_rate >= 0 AND completion_rate <= 1),
    CONSTRAINT chk_wh_satisfaction_new     CHECK (satisfaction >= 0 AND satisfaction <= 1)

) PARTITION BY RANGE (strt_dt);

COMMENT ON TABLE watch_history_new IS
    '시청 이력 파티션 테이블. strt_dt 기준 주별(일요일 시작, 7일 단위) 파티셔닝.';


-- =============================================================
-- [STEP 2] 주별 파티션 생성 (2023-01 데이터 범위)
-- 예상 소요: 5초
-- 파티션 경계: 매주 일요일 00:00:00 UTC 기준
-- =============================================================

-- 1주차: 2023-01-01(일) ~ 2023-01-07(토) — P03 테스트 쿼리 범위
CREATE TABLE watch_history_20230101
    PARTITION OF watch_history_new
    FOR VALUES FROM ('2023-01-01 00:00:00+00') TO ('2023-01-08 00:00:00+00');

-- 2주차: 2023-01-08(일) ~ 2023-01-14(토)
CREATE TABLE watch_history_20230108
    PARTITION OF watch_history_new
    FOR VALUES FROM ('2023-01-08 00:00:00+00') TO ('2023-01-15 00:00:00+00');

-- 3주차: 2023-01-15(일) ~ 2023-01-21(토)
CREATE TABLE watch_history_20230115
    PARTITION OF watch_history_new
    FOR VALUES FROM ('2023-01-15 00:00:00+00') TO ('2023-01-22 00:00:00+00');

-- 4주차: 2023-01-22(일) ~ 2023-01-28(토)
CREATE TABLE watch_history_20230122
    PARTITION OF watch_history_new
    FOR VALUES FROM ('2023-01-22 00:00:00+00') TO ('2023-01-29 00:00:00+00');

-- 5주차: 2023-01-29(일) ~ 2023-02-04(토) [월말 포함]
CREATE TABLE watch_history_20230129
    PARTITION OF watch_history_new
    FOR VALUES FROM ('2023-01-29 00:00:00+00') TO ('2023-02-05 00:00:00+00');


-- =============================================================
-- [STEP 3] DEFAULT 파티션 생성 (안전망)
-- 파티션 범위 외 데이터 유실 방지 — 향후 신규 데이터도 우선 여기에 적재됨
-- db_maintenance.py가 자동으로 주별 파티션을 미리 생성하므로 이곳이 차면 이상 신호
-- =============================================================

CREATE TABLE watch_history_default
    PARTITION OF watch_history_new DEFAULT;


-- =============================================================
-- [STEP 4] 데이터 복사: watch_history → watch_history_new
-- 예상 소요: 30~60분 (3.99M rows, FK 체크 없는 상태)
-- 주의: OVERRIDING SYSTEM VALUE로 기존 watch_history_id 그대로 보존
--       복사 완료 후 시퀀스를 현재 최댓값으로 동기화
-- =============================================================

INSERT INTO watch_history_new (
    watch_history_id,
    user_id_fk,
    vod_id_fk,
    strt_dt,
    use_tms,
    completion_rate,
    satisfaction,
    created_at
)
OVERRIDING SYSTEM VALUE
SELECT
    watch_history_id,
    user_id_fk,
    vod_id_fk,
    strt_dt,
    use_tms,
    completion_rate,
    satisfaction,
    created_at
FROM watch_history;

-- 시퀀스 동기화 (새 INSERT가 기존 ID와 충돌하지 않도록)
SELECT setval(
    pg_get_serial_sequence('watch_history_new', 'watch_history_id'),
    (SELECT MAX(watch_history_id) FROM watch_history_new)
);

-- 복사 결과 확인
SELECT COUNT(*) AS copied_rows FROM watch_history_new;
-- 기대값: 3,992,530


-- =============================================================
-- [STEP 5] 외래키 제약 추가 (복사 완료 후 추가 — 성능 최적화)
-- 예상 소요: 10~20분 (전체 행 검증)
-- =============================================================

ALTER TABLE watch_history_new
    ADD CONSTRAINT fk_wh_user
        FOREIGN KEY (user_id_fk) REFERENCES "user"(sha2_hash)
        ON DELETE RESTRICT;

ALTER TABLE watch_history_new
    ADD CONSTRAINT fk_wh_vod
        FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id)
        ON DELETE RESTRICT;


-- =============================================================
-- [STEP 6] 인덱스 생성 (부모 테이블에 생성 → 모든 파티션에 자동 전파)
-- 예상 소요: 60~120분
-- PostgreSQL 11+: 부모 인덱스 생성 시 각 파티션에 동일 인덱스 자동 생성
-- =============================================================

-- [6-1] 사용자별 시청이력 조회 (P01, P05)
CREATE INDEX idx_wh_new_user_id
    ON watch_history_new (user_id_fk);

-- [6-2] VOD별 시청 통계 조회 (P02)
CREATE INDEX idx_wh_new_vod_id
    ON watch_history_new (vod_id_fk);

-- [6-3] 날짜 범위 조회 (P03)
CREATE INDEX idx_wh_new_strt_dt
    ON watch_history_new (strt_dt);

-- [6-4] 커버링 인덱스: P01 vod JOIN heap fetch 제거 (OPT-1-A 이관)
--        파티션 환경에서 strt_dt 범위가 파티션과 일치 → 파티션 내 Index Scan
CREATE INDEX idx_wh_new_user_covering
    ON watch_history_new (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);

-- [6-5] 부분 인덱스: satisfaction > 0 필터 (OPT-1-B 이관)
CREATE INDEX idx_wh_new_satisfaction_nonzero
    ON watch_history_new (satisfaction DESC)
    WHERE satisfaction > 0;

-- 인덱스 생성 확인
SELECT
    i.relname       AS index_name,
    t.relname       AS table_name,
    pg_size_pretty(pg_relation_size(i.oid)) AS index_size
FROM pg_class i
JOIN pg_index ix ON i.oid = ix.indexrelid
JOIN pg_class t  ON t.oid = ix.indrelid
WHERE t.relname LIKE 'watch_history_new%'
  AND i.relkind = 'i'
ORDER BY t.relname, i.relname;


-- =============================================================
-- [STEP 7] 검증: 행 수, 파티션 분포, 인덱스 확인
-- 이 단계에서 문제가 있으면 STEP 8 진행하지 않음
-- =============================================================

-- 7-1. 전체 행 수 확인 (기존과 일치해야 함)
SELECT COUNT(*) AS new_table_rows FROM watch_history_new;
-- 기대값: 3,992,530

-- 7-2. 파티션별 행 수 분포 확인
SELECT
    c.relname       AS partition_name,
    p.reltuples::BIGINT AS estimated_rows,
    pg_size_pretty(pg_total_relation_size(c.oid)) AS total_size
FROM pg_class c
JOIN pg_inherits i ON c.oid = i.inhrelid
JOIN pg_class p    ON p.oid = i.inhparent
WHERE p.relname = 'watch_history_new'
ORDER BY c.relname;

-- 7-3. 기존 테이블과 행 수 비교
SELECT
    (SELECT COUNT(*) FROM watch_history)     AS old_count,
    (SELECT COUNT(*) FROM watch_history_new) AS new_count,
    (SELECT COUNT(*) FROM watch_history)
        = (SELECT COUNT(*) FROM watch_history_new) AS counts_match;

-- 7-4. DEFAULT 파티션 데이터 유무 확인 (있으면 범위 밖 데이터 존재)
SELECT COUNT(*) AS default_partition_rows FROM watch_history_default;
-- 기대값: 0


-- =============================================================
-- [STEP 8] 테이블 스왑 (원자적 트랜잭션)
-- 예상 소요: 1~2초 (명칭 변경만)
-- 주의: 이 블록 실행 중 write 트래픽이 있으면 brief lock 발생
--       심야 배치 시간(db_maintenance.py 실행 직후)에 수행 권장
-- =============================================================

BEGIN;

-- 기존 테이블 백업 이름으로 변경
ALTER TABLE watch_history     RENAME TO watch_history_old;

-- 새 파티션 테이블을 운영 이름으로 변경
ALTER TABLE watch_history_new RENAME TO watch_history;

COMMIT;

-- 스왑 확인
SELECT
    schemaname,
    tablename,
    tableowner
FROM pg_tables
WHERE tablename IN ('watch_history', 'watch_history_old', 'watch_history_new')
ORDER BY tablename;


-- =============================================================
-- [STEP 9] 구 테이블 삭제 (검증 완료 후 수동 실행)
-- 주의: 삭제 후 복구 불가. 최소 24시간 운용 후 이상 없을 때 실행.
-- =============================================================

-- DROP TABLE watch_history_old;  -- 검증 완료 후 주석 해제하여 실행


-- =============================================================
-- [최종 확인] 파티션 정보 및 인덱스 전파 확인
-- =============================================================

-- 파티션 목록 및 경계 확인
SELECT
    child.relname                           AS partition_name,
    pg_get_expr(child_c.relpartbound, child.oid, TRUE) AS partition_range
FROM pg_class parent
JOIN pg_inherits i      ON parent.oid = i.inhparent
JOIN pg_class child     ON child.oid  = i.inhrelid
JOIN pg_class child_c   ON child_c.oid = i.inhrelid  -- pg 15+
WHERE parent.relname = 'watch_history'
ORDER BY child.relname;

-- 파티션별 인덱스 확인 (각 파티션에 인덱스가 전파되었는지 확인)
SELECT
    t.relname   AS partition,
    i.relname   AS index_name
FROM pg_class i
JOIN pg_index ix ON i.oid = ix.indexrelid
JOIN pg_class t  ON t.oid = ix.indrelid
WHERE t.relname LIKE 'watch_history_2023%'
   OR t.relname = 'watch_history_default'
ORDER BY t.relname, i.relname;
