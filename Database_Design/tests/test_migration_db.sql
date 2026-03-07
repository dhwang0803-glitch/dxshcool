-- =============================================================
-- Phase 2 Migration - DB 통합 테스트 (마이그레이션 완료 후 실행)
-- 파일: Database_Design/tests/test_migration_db.sql
-- 목적: CSV 적재 완료 후 VPC DB 상태를 검증하는 통합 테스트
-- 작성일: 2026-03-07
-- 참조: PLAN_02_DATA_MIGRATION.md
-- =============================================================
-- 실행 방법: psql -U <user> -d vod_db -f test_migration_db.sql
-- 전제 조건: migrate.py 실행 완료 후 실행
-- 모든 테스트가 RAISE EXCEPTION 없이 통과하면 마이그레이션 완료
-- =============================================================


-- =============================================================
-- [섹션 1] 건수 검증 (T01~T03)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T01: user 테이블 건수 검증
-- 목적: user 테이블에 CSV 원본 전체 건수가 적재되었는지 확인
-- 기대값: 242,702건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 242702;
BEGIN
    SELECT COUNT(*) INTO v_count FROM "user";

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T01 FAIL] user 테이블 건수 불일치. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T01 PASS] user 테이블 건수 확인: %건', v_count;
END $$;


-- -------------------------------------------------------------
-- 테스트 T02: vod 테이블 건수 검증
-- 목적: vod 테이블에 CSV 원본 전체 건수가 적재되었는지 확인
-- 기대값: 166,159건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 166159;
BEGIN
    SELECT COUNT(*) INTO v_count FROM vod;

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T02 FAIL] vod 테이블 건수 불일치. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T02 PASS] vod 테이블 건수 확인: %건', v_count;
END $$;


-- -------------------------------------------------------------
-- 테스트 T03: watch_history 테이블 건수 검증
-- 목적: watch_history 테이블에 CSV 원본 전체 건수가 적재되었는지 확인
-- 기대값: 3,992,530건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 3992530;
BEGIN
    SELECT COUNT(*) INTO v_count FROM watch_history;

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T03 FAIL] watch_history 테이블 건수 불일치. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T03 PASS] watch_history 테이블 건수 확인: %건', v_count;
END $$;


-- =============================================================
-- [섹션 2] FK 무결성 (T04~T05)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T04: watch_history -> user FK 무결성
-- 목적: watch_history.user_id_fk 중 user 테이블에 존재하지 않는
--       orphan 레코드가 없는지 확인
-- 기대값: 0건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM watch_history wh
    LEFT JOIN "user" u ON wh.user_id_fk = u.sha2_hash
    WHERE u.sha2_hash IS NULL;

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T04 FAIL] watch_history -> user orphan 레코드 존재. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T04 PASS] watch_history -> user FK 무결성 확인: orphan %건', v_count;
END $$;


-- -------------------------------------------------------------
-- 테스트 T05: watch_history -> vod FK 무결성
-- 목적: watch_history.vod_id_fk 중 vod 테이블에 존재하지 않는
--       orphan 레코드가 없는지 확인
-- 기대값: 0건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM watch_history wh
    LEFT JOIN vod v ON wh.vod_id_fk = v.full_asset_id
    WHERE v.full_asset_id IS NULL;

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T05 FAIL] watch_history -> vod orphan 레코드 존재. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T05 PASS] watch_history -> vod FK 무결성 확인: orphan %건', v_count;
END $$;


-- =============================================================
-- [섹션 3] 데이터 품질 (T06~T08)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T06: completion_rate 범위 검증 (0 ~ 1)
-- 목적: completion_rate 컬럼에 범위를 초과하는 값(>1 또는 <0)이
--       없는지 확인 (클리핑 변환이 올바르게 적용되었는지 검증)
-- 기대값: 범위 초과값 0건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM watch_history
    WHERE completion_rate < 0
       OR completion_rate > 1;

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T06 FAIL] completion_rate 범위 초과 레코드 존재. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T06 PASS] completion_rate 범위(0~1) 검증: 범위 초과 %건', v_count;
END $$;


-- -------------------------------------------------------------
-- 테스트 T07: satisfaction 범위 검증 (0 ~ 1)
-- 목적: satisfaction 컬럼에 범위를 초과하는 값(>1 또는 <0)이
--       없는지 확인
-- 기대값: 범위 초과값 0건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM watch_history
    WHERE satisfaction < 0
       OR satisfaction > 1;

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T07 FAIL] satisfaction 범위 초과 레코드 존재. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T07 PASS] satisfaction 범위(0~1) 검증: 범위 초과 %건', v_count;
END $$;


-- -------------------------------------------------------------
-- 테스트 T08: use_tms 음수값 검증 (>= 0)
-- 목적: use_tms(시청 시간, 초) 컬럼에 음수값이 없는지 확인
--       (CHECK 제약조건 및 데이터 적재 정합성 검증)
-- 기대값: 음수값 0건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count  BIGINT;
    v_expect BIGINT := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM watch_history
    WHERE use_tms < 0;

    IF v_count <> v_expect THEN
        RAISE EXCEPTION '[T08 FAIL] use_tms 음수 레코드 존재. 기대값: %, 실제값: %',
            v_expect, v_count;
    END IF;
    RAISE NOTICE '[T08 PASS] use_tms >= 0 검증: 음수 %건', v_count;
END $$;


-- =============================================================
-- [섹션 4] 변환 검증 (T09~T10)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T09: user.nfx_use_yn BOOLEAN 변환 검증
-- 목적: user.nfx_use_yn 컬럼에 NULL이 없고 TRUE/FALSE만 존재하는지 확인
--       ("Y"/"N" -> TRUE/FALSE 변환이 완전히 적용되었는지 검증)
-- 기대값: NULL 레코드 0건
-- -------------------------------------------------------------
DO $$
DECLARE
    v_null_count BIGINT;
    v_expect     BIGINT := 0;
BEGIN
    SELECT COUNT(*)
    INTO v_null_count
    FROM "user"
    WHERE nfx_use_yn IS NULL;

    IF v_null_count <> v_expect THEN
        RAISE EXCEPTION '[T09 FAIL] user.nfx_use_yn에 NULL 레코드 존재. 기대값: %, 실제값: %',
            v_expect, v_null_count;
    END IF;
    RAISE NOTICE '[T09 PASS] user.nfx_use_yn BOOLEAN 변환 완료: NULL %건', v_null_count;
END $$;


-- -------------------------------------------------------------
-- 테스트 T10: vod.disp_rtm_sec 변환 유효성 검증
-- 목적: disp_rtm_sec > 0 인 레코드가 전체 vod의 95% 이상인지 확인
--       (HH:MM / HH:MM:SS -> 초 변환이 대부분 정상 처리되었는지 검증)
-- 기대값: disp_rtm_sec > 0 비율 >= 95%
-- -------------------------------------------------------------
DO $$
DECLARE
    v_total       BIGINT;
    v_valid       BIGINT;
    v_ratio       NUMERIC(5,2);
    v_min_ratio   NUMERIC(5,2) := 95.00;
BEGIN
    SELECT COUNT(*) INTO v_total FROM vod;
    SELECT COUNT(*) INTO v_valid FROM vod WHERE disp_rtm_sec > 0;

    IF v_total = 0 THEN
        RAISE EXCEPTION '[T10 FAIL] vod 테이블에 데이터가 없습니다.';
    END IF;

    v_ratio := ROUND((v_valid::NUMERIC / v_total::NUMERIC) * 100, 2);

    IF v_ratio < v_min_ratio THEN
        RAISE EXCEPTION '[T10 FAIL] disp_rtm_sec > 0 비율 부족. 기대값: >= %%, 실제값: %%',
            v_min_ratio, v_ratio;
    END IF;
    RAISE NOTICE '[T10 PASS] vod.disp_rtm_sec > 0 비율: %%  (유효: %건 / 전체: %건)',
        v_ratio, v_valid, v_total;
END $$;


-- =============================================================
-- [섹션 5] 만족도 분포 (T11~T12)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T11: satisfaction = 0 레코드 존재 확인
-- 목적: satisfaction이 0인 레코드가 실제로 존재하는지 확인
--       설계 요구사항 근사값 1,006,961건 기준으로 ±5% 허용 범위 검증
-- 기대값: 1,006,961건 (±5% 허용: 956,613 ~ 1,057,309)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count      BIGINT;
    v_expect     BIGINT := 1006961;
    v_tolerance  NUMERIC := 0.05;  -- 5% 허용 오차
    v_lower      BIGINT;
    v_upper      BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM watch_history
    WHERE satisfaction = 0;

    v_lower := FLOOR(v_expect * (1 - v_tolerance));
    v_upper := CEIL(v_expect  * (1 + v_tolerance));

    IF v_count = 0 THEN
        RAISE EXCEPTION '[T11 FAIL] satisfaction = 0 레코드가 존재하지 않습니다. 실제값: %',
            v_count;
    END IF;

    IF v_count < v_lower OR v_count > v_upper THEN
        RAISE EXCEPTION '[T11 FAIL] satisfaction = 0 건수가 허용 범위 초과. 기대범위: %~%, 실제값: %',
            v_lower, v_upper, v_count;
    END IF;
    RAISE NOTICE '[T11 PASS] satisfaction = 0 건수 확인: %건 (기대 근사: %건, 허용범위: %~%)',
        v_count, v_expect, v_lower, v_upper;
END $$;


-- -------------------------------------------------------------
-- 테스트 T12: satisfaction > 0 레코드 존재 확인
-- 목적: satisfaction이 0 초과인 레코드가 실제로 존재하는지 확인
--       설계 요구사항 근사값 2,985,569건 기준으로 ±5% 허용 범위 검증
-- 기대값: 2,985,569건 (±5% 허용: 2,836,291 ~ 3,134,848)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count      BIGINT;
    v_expect     BIGINT := 2985569;
    v_tolerance  NUMERIC := 0.05;  -- 5% 허용 오차
    v_lower      BIGINT;
    v_upper      BIGINT;
BEGIN
    SELECT COUNT(*) INTO v_count
    FROM watch_history
    WHERE satisfaction > 0;

    v_lower := FLOOR(v_expect * (1 - v_tolerance));
    v_upper := CEIL(v_expect  * (1 + v_tolerance));

    IF v_count = 0 THEN
        RAISE EXCEPTION '[T12 FAIL] satisfaction > 0 레코드가 존재하지 않습니다. 실제값: %',
            v_count;
    END IF;

    IF v_count < v_lower OR v_count > v_upper THEN
        RAISE EXCEPTION '[T12 FAIL] satisfaction > 0 건수가 허용 범위 초과. 기대범위: %~%, 실제값: %',
            v_lower, v_upper, v_count;
    END IF;
    RAISE NOTICE '[T12 PASS] satisfaction > 0 건수 확인: %건 (기대 근사: %건, 허용범위: %~%)',
        v_count, v_expect, v_lower, v_upper;
END $$;


-- =============================================================
-- 전체 테스트 완료 알림
-- =============================================================
DO $$
BEGIN
    RAISE NOTICE '================================================';
    RAISE NOTICE 'Phase 2 Migration DB 통합 테스트 전체 완료';
    RAISE NOTICE '총 12건 | T01~T03: 건수 | T04~T05: FK 무결성';
    RAISE NOTICE 'T06~T08: 데이터 품질 | T09~T10: 변환 검증';
    RAISE NOTICE 'T11~T12: 만족도 분포';
    RAISE NOTICE '================================================';
END $$;
