-- =============================================================
-- Phase 1 Schema DDL - TDD Red 단계 테스트
-- 파일: Database_Design/tests/test_schema.sql
-- 목적: 구현 전 실패하는 테스트를 먼저 작성 (TDD Red)
-- 작성일: 2026-03-07
-- 참조: PLAN_01_SCHEMA_DDL.md
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f test_schema.sql
-- 모든 테스트가 RAISE EXCEPTION 없이 통과하면 구현 완료
-- =============================================================


-- =============================================================
-- [섹션 1] 테이블 존재 확인 (3건)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T01: "user" 테이블 존재 확인
-- 목적: "user" 테이블이 public 스키마에 생성되어 있는지 검증
-- 기대값: 테이블 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND table_type = 'BASE TABLE';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T01 FAIL] "user" 테이블이 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T01 PASS] "user" 테이블 존재 확인';
END $$;


-- -------------------------------------------------------------
-- 테스트 T02: vod 테이블 존재 확인
-- 목적: vod 테이블이 public 스키마에 생성되어 있는지 검증
-- 기대값: 테이블 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND table_type = 'BASE TABLE';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T02 FAIL] vod 테이블이 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T02 PASS] vod 테이블 존재 확인';
END $$;


-- -------------------------------------------------------------
-- 테스트 T03: watch_history 테이블 존재 확인
-- 목적: watch_history 테이블이 public 스키마에 생성되어 있는지 검증
-- 기대값: 테이블 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND table_type = 'BASE TABLE';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T03 FAIL] watch_history 테이블이 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T03 PASS] watch_history 테이블 존재 확인';
END $$;


-- =============================================================
-- [섹션 2] "user" 테이블 컬럼 및 타입 확인 (10건)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T04: user.sha2_hash - VARCHAR(64), PRIMARY KEY
-- 목적: sha2_hash 컬럼의 타입과 길이가 VARCHAR(64)인지 검증
-- 기대값: character_maximum_length = 64
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'sha2_hash'
      AND data_type = 'character varying'
      AND character_maximum_length = 64;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T04 FAIL] user.sha2_hash 컬럼이 VARCHAR(64)가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T04 PASS] user.sha2_hash VARCHAR(64) 타입 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T05: user.sha2_hash - PRIMARY KEY 확인
-- 목적: sha2_hash가 "user" 테이블의 PRIMARY KEY인지 검증
-- 기대값: PK 제약조건 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.table_schema = 'public'
      AND tc.table_name = 'user'
      AND tc.constraint_type = 'PRIMARY KEY'
      AND kcu.column_name = 'sha2_hash';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T05 FAIL] user.sha2_hash가 PRIMARY KEY가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T05 PASS] user.sha2_hash PRIMARY KEY 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T06: user.age_grp10 - VARCHAR(16), NOT NULL
-- 목적: age_grp10 컬럼의 타입, 길이, NOT NULL 제약 검증
-- 기대값: VARCHAR(16), is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'age_grp10'
      AND data_type = 'character varying'
      AND character_maximum_length = 16
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T06 FAIL] user.age_grp10 컬럼이 VARCHAR(16) NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T06 PASS] user.age_grp10 VARCHAR(16) NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T07: user.inhome_rate - REAL, NULL 허용
-- 목적: inhome_rate 컬럼의 타입이 REAL이고 NULL 허용인지 검증
-- 기대값: data_type = 'real', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'inhome_rate'
      AND data_type = 'real'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T07 FAIL] user.inhome_rate 컬럼이 REAL NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T07 PASS] user.inhome_rate REAL NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T08: user.svod_scrb_cnt_grp - VARCHAR(16), NULL 허용
-- 목적: svod_scrb_cnt_grp 컬럼의 타입과 NULL 허용 여부 검증
-- 기대값: VARCHAR(16), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'svod_scrb_cnt_grp'
      AND data_type = 'character varying'
      AND character_maximum_length = 16
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T08 FAIL] user.svod_scrb_cnt_grp 컬럼이 VARCHAR(16) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T08 PASS] user.svod_scrb_cnt_grp VARCHAR(16) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T09: user.paid_chnl_cnt_grp - VARCHAR(16), NULL 허용
-- 목적: paid_chnl_cnt_grp 컬럼의 타입과 NULL 허용 여부 검증
-- 기대값: VARCHAR(16), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'paid_chnl_cnt_grp'
      AND data_type = 'character varying'
      AND character_maximum_length = 16
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T09 FAIL] user.paid_chnl_cnt_grp 컬럼이 VARCHAR(16) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T09 PASS] user.paid_chnl_cnt_grp VARCHAR(16) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T10: user.ch_hh_avg_month1 - REAL, NULL 허용
-- 목적: ch_hh_avg_month1 컬럼의 타입이 REAL이고 NULL 허용인지 검증
-- 기대값: data_type = 'real', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'ch_hh_avg_month1'
      AND data_type = 'real'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T10 FAIL] user.ch_hh_avg_month1 컬럼이 REAL NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T10 PASS] user.ch_hh_avg_month1 REAL NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T11: user.kids_use_pv_month1 - REAL, NULL 허용
-- 목적: kids_use_pv_month1 컬럼의 타입이 REAL이고 NULL 허용인지 검증
-- 기대값: data_type = 'real', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'kids_use_pv_month1'
      AND data_type = 'real'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T11 FAIL] user.kids_use_pv_month1 컬럼이 REAL NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T11 PASS] user.kids_use_pv_month1 REAL NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T12: user.nfx_use_yn - BOOLEAN, NULL 허용
-- 목적: nfx_use_yn 컬럼의 타입이 BOOLEAN이고 NULL 허용인지 검증
-- 기대값: data_type = 'boolean', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'nfx_use_yn'
      AND data_type = 'boolean'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T12 FAIL] user.nfx_use_yn 컬럼이 BOOLEAN NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T12 PASS] user.nfx_use_yn BOOLEAN NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T13: user.created_at - TIMESTAMPTZ, DEFAULT NOW()
-- 목적: created_at 컬럼의 타입이 TIMESTAMPTZ이고 DEFAULT가 설정되어 있는지 검증
-- 기대값: data_type = 'timestamp with time zone', column_default IS NOT NULL
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'created_at'
      AND data_type = 'timestamp with time zone'
      AND column_default IS NOT NULL;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T13 FAIL] user.created_at 컬럼이 TIMESTAMPTZ DEFAULT NOW()가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T13 PASS] user.created_at TIMESTAMPTZ DEFAULT NOW() 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T14: user.last_active_at - TIMESTAMPTZ, DEFAULT NOW()
-- 목적: last_active_at 컬럼의 타입이 TIMESTAMPTZ이고 DEFAULT가 설정되어 있는지 검증
-- 기대값: data_type = 'timestamp with time zone', column_default IS NOT NULL
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'user'
      AND column_name = 'last_active_at'
      AND data_type = 'timestamp with time zone'
      AND column_default IS NOT NULL;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T14 FAIL] user.last_active_at 컬럼이 TIMESTAMPTZ DEFAULT NOW()가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T14 PASS] user.last_active_at TIMESTAMPTZ DEFAULT NOW() 확인';
END $$;


-- =============================================================
-- [섹션 3] vod 테이블 컬럼 및 타입 확인 (17건)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T15: vod.full_asset_id - VARCHAR(64), PRIMARY KEY
-- 목적: full_asset_id 컬럼의 타입이 VARCHAR(64)인지 검증
-- 기대값: character_maximum_length = 64
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'full_asset_id'
      AND data_type = 'character varying'
      AND character_maximum_length = 64;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T15 FAIL] vod.full_asset_id 컬럼이 VARCHAR(64)가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T15 PASS] vod.full_asset_id VARCHAR(64) 타입 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T16: vod.full_asset_id - PRIMARY KEY 확인
-- 목적: full_asset_id가 vod 테이블의 PRIMARY KEY인지 검증
-- 기대값: PK 제약조건 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.table_schema = 'public'
      AND tc.table_name = 'vod'
      AND tc.constraint_type = 'PRIMARY KEY'
      AND kcu.column_name = 'full_asset_id';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T16 FAIL] vod.full_asset_id가 PRIMARY KEY가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T16 PASS] vod.full_asset_id PRIMARY KEY 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T17: vod.asset_nm - VARCHAR(255), NOT NULL
-- 목적: asset_nm 컬럼의 타입, 길이, NOT NULL 제약 검증
-- 기대값: VARCHAR(255), is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'asset_nm'
      AND data_type = 'character varying'
      AND character_maximum_length = 255
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T17 FAIL] vod.asset_nm 컬럼이 VARCHAR(255) NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T17 PASS] vod.asset_nm VARCHAR(255) NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T18: vod.ct_cl - VARCHAR(32), NOT NULL
-- 목적: ct_cl 컬럼의 타입, 길이, NOT NULL 제약 검증
-- 기대값: VARCHAR(32), is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'ct_cl'
      AND data_type = 'character varying'
      AND character_maximum_length = 32
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T18 FAIL] vod.ct_cl 컬럼이 VARCHAR(32) NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T18 PASS] vod.ct_cl VARCHAR(32) NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T19: vod.disp_rtm - VARCHAR(8), NULL 허용
-- 목적: disp_rtm 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(8), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'disp_rtm'
      AND data_type = 'character varying'
      AND character_maximum_length = 8
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T19 FAIL] vod.disp_rtm 컬럼이 VARCHAR(8) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T19 PASS] vod.disp_rtm VARCHAR(8) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T20: vod.disp_rtm_sec - INTEGER, NOT NULL
-- 목적: disp_rtm_sec 컬럼의 타입이 INTEGER이고 NOT NULL인지 검증
-- 기대값: data_type = 'integer', is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'disp_rtm_sec'
      AND data_type = 'integer'
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T20 FAIL] vod.disp_rtm_sec 컬럼이 INTEGER NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T20 PASS] vod.disp_rtm_sec INTEGER NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T21: vod.genre - VARCHAR(64), NULL 허용
-- 목적: genre 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(64), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'genre'
      AND data_type = 'character varying'
      AND character_maximum_length = 64
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T21 FAIL] vod.genre 컬럼이 VARCHAR(64) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T21 PASS] vod.genre VARCHAR(64) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T22: vod.director - VARCHAR(255), NULL 허용 (RAG 대상)
-- 목적: director 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(255), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'director'
      AND data_type = 'character varying'
      AND character_maximum_length = 255
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T22 FAIL] vod.director 컬럼이 VARCHAR(255) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T22 PASS] vod.director VARCHAR(255) NULL 허용 확인 (RAG 대상)';
END $$;

-- -------------------------------------------------------------
-- 테스트 T23: vod.asset_prod - VARCHAR(64), NULL 허용
-- 목적: asset_prod 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(64), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'asset_prod'
      AND data_type = 'character varying'
      AND character_maximum_length = 64
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T23 FAIL] vod.asset_prod 컬럼이 VARCHAR(64) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T23 PASS] vod.asset_prod VARCHAR(64) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T24: vod.smry - TEXT, NULL 허용 (RAG 대상)
-- 목적: smry 컬럼의 타입이 TEXT이고 NULL 허용인지 검증
-- 기대값: data_type = 'text', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'smry'
      AND data_type = 'text'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T24 FAIL] vod.smry 컬럼이 TEXT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T24 PASS] vod.smry TEXT NULL 허용 확인 (RAG 대상)';
END $$;

-- -------------------------------------------------------------
-- 테스트 T25: vod.provider - VARCHAR(128), NULL 허용
-- 목적: provider 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(128), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'provider'
      AND data_type = 'character varying'
      AND character_maximum_length = 128
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T25 FAIL] vod.provider 컬럼이 VARCHAR(128) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T25 PASS] vod.provider VARCHAR(128) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T26: vod.genre_detail - VARCHAR(255), NULL 허용
-- 목적: genre_detail 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(255), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'genre_detail'
      AND data_type = 'character varying'
      AND character_maximum_length = 255
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T26 FAIL] vod.genre_detail 컬럼이 VARCHAR(255) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T26 PASS] vod.genre_detail VARCHAR(255) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T27: vod.series_nm - VARCHAR(255), NULL 허용
-- 목적: series_nm 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(255), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'series_nm'
      AND data_type = 'character varying'
      AND character_maximum_length = 255
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T27 FAIL] vod.series_nm 컬럼이 VARCHAR(255) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T27 PASS] vod.series_nm VARCHAR(255) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T28: vod.created_at - TIMESTAMPTZ, DEFAULT NOW()
-- 목적: created_at 컬럼의 타입이 TIMESTAMPTZ이고 DEFAULT가 설정되어 있는지 검증
-- 기대값: data_type = 'timestamp with time zone', column_default IS NOT NULL
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'created_at'
      AND data_type = 'timestamp with time zone'
      AND column_default IS NOT NULL;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T28 FAIL] vod.created_at 컬럼이 TIMESTAMPTZ DEFAULT NOW()가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T28 PASS] vod.created_at TIMESTAMPTZ DEFAULT NOW() 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T29: vod.updated_at - TIMESTAMPTZ, DEFAULT NOW()
-- 목적: updated_at 컬럼의 타입이 TIMESTAMPTZ이고 DEFAULT가 설정되어 있는지 검증
-- 기대값: data_type = 'timestamp with time zone', column_default IS NOT NULL
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'updated_at'
      AND data_type = 'timestamp with time zone'
      AND column_default IS NOT NULL;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T29 FAIL] vod.updated_at 컬럼이 TIMESTAMPTZ DEFAULT NOW()가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T29 PASS] vod.updated_at TIMESTAMPTZ DEFAULT NOW() 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T30: vod.rag_processed - BOOLEAN, DEFAULT FALSE
-- 목적: rag_processed 컬럼의 타입이 BOOLEAN이고 DEFAULT FALSE인지 검증
-- 기대값: data_type = 'boolean', column_default = 'false'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'rag_processed'
      AND data_type = 'boolean'
      AND column_default = 'false';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T30 FAIL] vod.rag_processed 컬럼이 BOOLEAN DEFAULT FALSE가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T30 PASS] vod.rag_processed BOOLEAN DEFAULT FALSE 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T31: vod.rag_source - VARCHAR(64), NULL 허용
-- 목적: rag_source 컬럼의 타입, 길이, NULL 허용 여부 검증
-- 기대값: VARCHAR(64), is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'rag_source'
      AND data_type = 'character varying'
      AND character_maximum_length = 64
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T31 FAIL] vod.rag_source 컬럼이 VARCHAR(64) NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T31 PASS] vod.rag_source VARCHAR(64) NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T32: vod.rag_processed_at - TIMESTAMPTZ, NULL 허용
-- 목적: rag_processed_at 컬럼의 타입이 TIMESTAMPTZ이고 NULL 허용인지 검증
-- 기대값: data_type = 'timestamp with time zone', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'vod'
      AND column_name = 'rag_processed_at'
      AND data_type = 'timestamp with time zone'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T32 FAIL] vod.rag_processed_at 컬럼이 TIMESTAMPTZ NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T32 PASS] vod.rag_processed_at TIMESTAMPTZ NULL 허용 확인';
END $$;


-- =============================================================
-- [섹션 4] watch_history 테이블 컬럼 및 타입 확인 (8건)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T33: watch_history.watch_history_id - BIGINT, PK, GENERATED ALWAYS AS IDENTITY
-- 목적: watch_history_id 컬럼의 타입이 BIGINT이고 IDENTITY 속성인지 검증
-- 기대값: data_type = 'bigint', is_identity = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'watch_history_id'
      AND data_type = 'bigint'
      AND is_identity = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T33 FAIL] watch_history.watch_history_id 컬럼이 BIGINT GENERATED ALWAYS AS IDENTITY가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T33 PASS] watch_history.watch_history_id BIGINT IDENTITY 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T34: watch_history.watch_history_id - PRIMARY KEY 확인
-- 목적: watch_history_id가 watch_history 테이블의 PRIMARY KEY인지 검증
-- 기대값: PK 제약조건 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
      ON tc.constraint_name = kcu.constraint_name
     AND tc.table_schema = kcu.table_schema
    WHERE tc.table_schema = 'public'
      AND tc.table_name = 'watch_history'
      AND tc.constraint_type = 'PRIMARY KEY'
      AND kcu.column_name = 'watch_history_id';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T34 FAIL] watch_history.watch_history_id가 PRIMARY KEY가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T34 PASS] watch_history.watch_history_id PRIMARY KEY 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T35: watch_history.user_id_fk - VARCHAR(64), NOT NULL, FK → "user".sha2_hash
-- 목적: user_id_fk 컬럼의 타입, NOT NULL 여부 검증
-- 기대값: VARCHAR(64), is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'user_id_fk'
      AND data_type = 'character varying'
      AND character_maximum_length = 64
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T35 FAIL] watch_history.user_id_fk 컬럼이 VARCHAR(64) NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T35 PASS] watch_history.user_id_fk VARCHAR(64) NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T36: watch_history.user_id_fk - FK → "user".sha2_hash 확인
-- 목적: user_id_fk가 "user".sha2_hash를 참조하는 FOREIGN KEY인지 검증
-- 기대값: FK 제약조건 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.referential_constraints rc
    JOIN information_schema.key_column_usage kcu_fk
      ON rc.constraint_name = kcu_fk.constraint_name
     AND rc.constraint_schema = kcu_fk.table_schema
    JOIN information_schema.key_column_usage kcu_pk
      ON rc.unique_constraint_name = kcu_pk.constraint_name
     AND rc.unique_constraint_schema = kcu_pk.table_schema
    WHERE kcu_fk.table_schema = 'public'
      AND kcu_fk.table_name = 'watch_history'
      AND kcu_fk.column_name = 'user_id_fk'
      AND kcu_pk.table_name = 'user'
      AND kcu_pk.column_name = 'sha2_hash';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T36 FAIL] watch_history.user_id_fk → "user".sha2_hash FK가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T36 PASS] watch_history.user_id_fk → "user".sha2_hash FK 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T37: watch_history.vod_id_fk - VARCHAR(64), NOT NULL, FK → vod.full_asset_id
-- 목적: vod_id_fk 컬럼의 타입, NOT NULL 여부 검증
-- 기대값: VARCHAR(64), is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'vod_id_fk'
      AND data_type = 'character varying'
      AND character_maximum_length = 64
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T37 FAIL] watch_history.vod_id_fk 컬럼이 VARCHAR(64) NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T37 PASS] watch_history.vod_id_fk VARCHAR(64) NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T38: watch_history.vod_id_fk - FK → vod.full_asset_id 확인
-- 목적: vod_id_fk가 vod.full_asset_id를 참조하는 FOREIGN KEY인지 검증
-- 기대값: FK 제약조건 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.referential_constraints rc
    JOIN information_schema.key_column_usage kcu_fk
      ON rc.constraint_name = kcu_fk.constraint_name
     AND rc.constraint_schema = kcu_fk.table_schema
    JOIN information_schema.key_column_usage kcu_pk
      ON rc.unique_constraint_name = kcu_pk.constraint_name
     AND rc.unique_constraint_schema = kcu_pk.table_schema
    WHERE kcu_fk.table_schema = 'public'
      AND kcu_fk.table_name = 'watch_history'
      AND kcu_fk.column_name = 'vod_id_fk'
      AND kcu_pk.table_name = 'vod'
      AND kcu_pk.column_name = 'full_asset_id';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T38 FAIL] watch_history.vod_id_fk → vod.full_asset_id FK가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T38 PASS] watch_history.vod_id_fk → vod.full_asset_id FK 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T39: watch_history.strt_dt - TIMESTAMPTZ, NOT NULL
-- 목적: strt_dt 컬럼의 타입이 TIMESTAMPTZ이고 NOT NULL인지 검증
-- 기대값: data_type = 'timestamp with time zone', is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'strt_dt'
      AND data_type = 'timestamp with time zone'
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T39 FAIL] watch_history.strt_dt 컬럼이 TIMESTAMPTZ NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T39 PASS] watch_history.strt_dt TIMESTAMPTZ NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T40: watch_history.use_tms - REAL, NOT NULL
-- 목적: use_tms 컬럼의 타입이 REAL이고 NOT NULL인지 검증
-- 기대값: data_type = 'real', is_nullable = 'NO'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'use_tms'
      AND data_type = 'real'
      AND is_nullable = 'NO';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T40 FAIL] watch_history.use_tms 컬럼이 REAL NOT NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T40 PASS] watch_history.use_tms REAL NOT NULL 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T41: watch_history.completion_rate - REAL, NULL 허용
-- 목적: completion_rate 컬럼의 타입이 REAL이고 NULL 허용인지 검증
-- 기대값: data_type = 'real', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'completion_rate'
      AND data_type = 'real'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T41 FAIL] watch_history.completion_rate 컬럼이 REAL NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T41 PASS] watch_history.completion_rate REAL NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T42: watch_history.satisfaction - REAL, NULL 허용
-- 목적: satisfaction 컬럼의 타입이 REAL이고 NULL 허용인지 검증
-- 기대값: data_type = 'real', is_nullable = 'YES'
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'satisfaction'
      AND data_type = 'real'
      AND is_nullable = 'YES';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T42 FAIL] watch_history.satisfaction 컬럼이 REAL NULL이 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T42 PASS] watch_history.satisfaction REAL NULL 허용 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T43: watch_history.created_at - TIMESTAMPTZ, DEFAULT NOW()
-- 목적: created_at 컬럼의 타입이 TIMESTAMPTZ이고 DEFAULT가 설정되어 있는지 검증
-- 기대값: data_type = 'timestamp with time zone', column_default IS NOT NULL
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'watch_history'
      AND column_name = 'created_at'
      AND data_type = 'timestamp with time zone'
      AND column_default IS NOT NULL;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T43 FAIL] watch_history.created_at 컬럼이 TIMESTAMPTZ DEFAULT NOW()가 아닙니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T43 PASS] watch_history.created_at TIMESTAMPTZ DEFAULT NOW() 확인';
END $$;


-- =============================================================
-- [섹션 5] 제약조건 확인 (4건)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T44: watch_history UNIQUE (user_id_fk, vod_id_fk, strt_dt)
-- 목적: 동일 사용자·VOD·시작시각 중복 방지를 위한 복합 UNIQUE 제약 검증
-- 기대값: UNIQUE 제약조건 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM (
        SELECT tc.constraint_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema = kcu.table_schema
        WHERE tc.table_schema = 'public'
          AND tc.table_name = 'watch_history'
          AND tc.constraint_type = 'UNIQUE'
          AND kcu.column_name IN ('user_id_fk', 'vod_id_fk', 'strt_dt')
        GROUP BY tc.constraint_name
        HAVING COUNT(DISTINCT kcu.column_name) = 3
    ) sub;

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T44 FAIL] watch_history UNIQUE(user_id_fk, vod_id_fk, strt_dt) 제약이 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T44 PASS] watch_history UNIQUE(user_id_fk, vod_id_fk, strt_dt) 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T45: watch_history CHECK use_tms >= 0
-- 목적: use_tms 컬럼에 음수 시청시간 방지 CHECK 제약이 있는지 검증
-- 기대값: CHECK 제약조건 존재 (count >= 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.check_constraints cc
    JOIN information_schema.table_constraints tc
      ON cc.constraint_name = tc.constraint_name
     AND cc.constraint_schema = tc.table_schema
    WHERE tc.table_schema = 'public'
      AND tc.table_name = 'watch_history'
      AND cc.check_clause LIKE '%use_tms%'
      AND cc.check_clause LIKE '%0%';

    IF v_count < 1 THEN
        RAISE EXCEPTION '[T45 FAIL] watch_history.use_tms >= 0 CHECK 제약이 존재하지 않습니다. 기대값: >= 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T45 PASS] watch_history.use_tms >= 0 CHECK 제약 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T46: watch_history CHECK completion_rate >= 0 AND completion_rate <= 1
-- 목적: completion_rate 컬럼에 0~1 범위 CHECK 제약이 있는지 검증
-- 기대값: CHECK 제약조건 존재 (count >= 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.check_constraints cc
    JOIN information_schema.table_constraints tc
      ON cc.constraint_name = tc.constraint_name
     AND cc.constraint_schema = tc.table_schema
    WHERE tc.table_schema = 'public'
      AND tc.table_name = 'watch_history'
      AND cc.check_clause LIKE '%completion_rate%';

    IF v_count < 1 THEN
        RAISE EXCEPTION '[T46 FAIL] watch_history.completion_rate 범위 CHECK 제약이 존재하지 않습니다. 기대값: >= 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T46 PASS] watch_history.completion_rate 0~1 CHECK 제약 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T47: watch_history CHECK satisfaction >= 0 AND satisfaction <= 1
-- 목적: satisfaction 컬럼에 0~1 범위 CHECK 제약이 있는지 검증
-- 기대값: CHECK 제약조건 존재 (count >= 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.check_constraints cc
    JOIN information_schema.table_constraints tc
      ON cc.constraint_name = tc.constraint_name
     AND cc.constraint_schema = tc.table_schema
    WHERE tc.table_schema = 'public'
      AND tc.table_name = 'watch_history'
      AND cc.check_clause LIKE '%satisfaction%';

    IF v_count < 1 THEN
        RAISE EXCEPTION '[T47 FAIL] watch_history.satisfaction 범위 CHECK 제약이 존재하지 않습니다. 기대값: >= 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T47 PASS] watch_history.satisfaction 0~1 CHECK 제약 확인';
END $$;


-- =============================================================
-- [섹션 6] 인덱스 존재 확인 (11건)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T48: idx_wh_user_id 인덱스 존재 확인
-- 목적: watch_history(user_id_fk) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'watch_history'
      AND indexname = 'idx_wh_user_id';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T48 FAIL] idx_wh_user_id 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T48 PASS] idx_wh_user_id 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T49: idx_wh_vod_id 인덱스 존재 확인
-- 목적: watch_history(vod_id_fk) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'watch_history'
      AND indexname = 'idx_wh_vod_id';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T49 FAIL] idx_wh_vod_id 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T49 PASS] idx_wh_vod_id 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T50: idx_wh_strt_dt 인덱스 존재 확인
-- 목적: watch_history(strt_dt) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'watch_history'
      AND indexname = 'idx_wh_strt_dt';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T50 FAIL] idx_wh_strt_dt 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T50 PASS] idx_wh_strt_dt 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T51: idx_wh_satisfaction 인덱스 존재 확인
-- 목적: watch_history(satisfaction) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'watch_history'
      AND indexname = 'idx_wh_satisfaction';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T51 FAIL] idx_wh_satisfaction 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T51 PASS] idx_wh_satisfaction 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T52: idx_wh_user_strt 인덱스 존재 확인
-- 목적: watch_history(user_id_fk, strt_dt) 복합 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'watch_history'
      AND indexname = 'idx_wh_user_strt';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T52 FAIL] idx_wh_user_strt 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T52 PASS] idx_wh_user_strt 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T53: idx_vod_ct_cl 인덱스 존재 확인
-- 목적: vod(ct_cl) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'vod'
      AND indexname = 'idx_vod_ct_cl';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T53 FAIL] idx_vod_ct_cl 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T53 PASS] idx_vod_ct_cl 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T54: idx_vod_genre 인덱스 존재 확인
-- 목적: vod(genre) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'vod'
      AND indexname = 'idx_vod_genre';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T54 FAIL] idx_vod_genre 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T54 PASS] idx_vod_genre 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T55: idx_vod_provider 인덱스 존재 확인
-- 목적: vod(provider) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'vod'
      AND indexname = 'idx_vod_provider';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T55 FAIL] idx_vod_provider 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T55 PASS] idx_vod_provider 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T56: idx_user_age_grp 인덱스 존재 확인
-- 목적: "user"(age_grp10) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'user'
      AND indexname = 'idx_user_age_grp';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T56 FAIL] idx_user_age_grp 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T56 PASS] idx_user_age_grp 인덱스 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T57: idx_user_nfx 인덱스 존재 확인
-- 목적: "user"(nfx_use_yn) 인덱스가 생성되어 있는지 검증
-- 기대값: 인덱스 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_indexes
    WHERE schemaname = 'public'
      AND tablename = 'user'
      AND indexname = 'idx_user_nfx';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T57 FAIL] idx_user_nfx 인덱스가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T57 PASS] idx_user_nfx 인덱스 존재 확인';
END $$;


-- =============================================================
-- [섹션 7] 트리거 확인 (3건)
-- =============================================================

-- -------------------------------------------------------------
-- 테스트 T58: update_updated_at_column 함수 존재 확인
-- 목적: updated_at 자동 갱신을 위한 트리거 함수가 존재하는지 검증
-- 기대값: 함수 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM pg_proc p
    JOIN pg_namespace n ON p.pronamespace = n.oid
    WHERE n.nspname = 'public'
      AND p.proname = 'update_updated_at_column';

    IF v_count <> 1 THEN
        RAISE EXCEPTION '[T58 FAIL] update_updated_at_column 함수가 존재하지 않습니다. 기대값: 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T58 PASS] update_updated_at_column 트리거 함수 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T59: trg_vod_updated_at 트리거 존재 확인
-- 목적: vod 테이블에 updated_at 자동 갱신 트리거가 존재하는지 검증
-- 기대값: 트리거 존재 (count = 1)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM information_schema.triggers
    WHERE trigger_schema = 'public'
      AND event_object_table = 'vod'
      AND trigger_name = 'trg_vod_updated_at';

    IF v_count < 1 THEN
        RAISE EXCEPTION '[T59 FAIL] trg_vod_updated_at 트리거가 존재하지 않습니다. 기대값: >= 1, 실제값: %', v_count;
    END IF;
    RAISE NOTICE '[T59 PASS] trg_vod_updated_at 트리거 존재 확인';
END $$;

-- -------------------------------------------------------------
-- 테스트 T60: trg_vod_updated_at 동작 검증 (UPDATE 시 updated_at 변경)
-- 목적: vod 테이블 UPDATE 시 updated_at이 자동으로 갱신되는지 동작 검증
-- 기대값: UPDATE 전후 updated_at 값이 달라짐 (v_updated_after > v_updated_before)
-- -------------------------------------------------------------
DO $$
DECLARE
    v_test_id        VARCHAR(64) := 'TEST_TRIGGER_VOD_ID_00001';
    v_updated_before TIMESTAMPTZ;
    v_updated_after  TIMESTAMPTZ;
BEGIN
    -- 테스트용 VOD 레코드 삽입 (updated_at 고정값으로 삽입)
    INSERT INTO vod (
        full_asset_id,
        asset_nm,
        ct_cl,
        disp_rtm_sec,
        updated_at
    ) VALUES (
        v_test_id,
        'TDD 트리거 테스트용 VOD',
        '테스트',
        600,
        '2000-01-01 00:00:00+00'
    );

    -- 삽입 직후 updated_at 기록
    SELECT updated_at INTO v_updated_before
    FROM vod
    WHERE full_asset_id = v_test_id;

    -- 잠시 대기 후 UPDATE 수행 (동일 타임스탬프 방지)
    PERFORM pg_sleep(0.01);

    -- asset_nm UPDATE → 트리거가 updated_at을 현재 시각으로 갱신해야 함
    UPDATE vod
    SET asset_nm = 'TDD 트리거 테스트용 VOD (수정됨)'
    WHERE full_asset_id = v_test_id;

    -- UPDATE 후 updated_at 기록
    SELECT updated_at INTO v_updated_after
    FROM vod
    WHERE full_asset_id = v_test_id;

    -- 검증: updated_at이 갱신되었는지 확인
    IF v_updated_after <= v_updated_before THEN
        -- 테스트 데이터 정리 후 실패 발생
        DELETE FROM vod WHERE full_asset_id = v_test_id;
        RAISE EXCEPTION '[T60 FAIL] trg_vod_updated_at 동작 실패: UPDATE 후 updated_at이 갱신되지 않았습니다. before=%, after=%',
            v_updated_before, v_updated_after;
    END IF;

    -- 테스트 데이터 정리
    DELETE FROM vod WHERE full_asset_id = v_test_id;

    RAISE NOTICE '[T60 PASS] trg_vod_updated_at 동작 검증: before=%, after=%',
        v_updated_before, v_updated_after;
END $$;


-- =============================================================
-- 테스트 완료 요약
-- =============================================================
DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Phase 1 Schema DDL TDD Red 단계 테스트 완료';
    RAISE NOTICE '총 테스트 항목: 60건';
    RAISE NOTICE '  - 섹션 1 (테이블 존재 확인):          T01 ~ T03  (3건)';
    RAISE NOTICE '  - 섹션 2 ("user" 컬럼/타입 확인):     T04 ~ T14 (11건)';
    RAISE NOTICE '  - 섹션 3 (vod 컬럼/타입 확인):        T15 ~ T32 (18건)';
    RAISE NOTICE '  - 섹션 4 (watch_history 컬럼/타입):   T33 ~ T43 (11건)';
    RAISE NOTICE '  - 섹션 5 (제약조건 확인):              T44 ~ T47  (4건)';
    RAISE NOTICE '  - 섹션 6 (인덱스 존재 확인):           T48 ~ T57 (10건)';
    RAISE NOTICE '  - 섹션 7 (트리거 확인):                T58 ~ T60  (3건)';
    RAISE NOTICE '============================================';
END $$;
