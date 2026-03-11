-- =============================================================
-- Phase 1: 핵심 스키마 DDL
-- 파일: Database_Design/schema/create_tables.sql
-- 목적: USER, VOD, WATCH_HISTORY 3개 핵심 테이블 생성
-- 작성일: 2026-03-07
-- 참조: PLAN_01_SCHEMA_DDL.md, PLAN_00_MASTER.md
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_tables.sql
-- 주의: create_indexes.sql 이전에 실행할 것
-- =============================================================


-- =============================================================
-- 1. 확장 모듈
-- =============================================================

-- pg_trgm: 퍼지 문자열 검색 지원 (LIKE '%...%' 인덱스 최적화)
CREATE EXTENSION IF NOT EXISTS pg_trgm;


-- =============================================================
-- 2. "user" 테이블
--    PostgreSQL 예약어이므로 따옴표 필수
--    PK: sha2_hash (SHA-2 해시된 사용자 식별자)
-- =============================================================

CREATE TABLE "user" (
    sha2_hash           VARCHAR(64)     PRIMARY KEY,
    age_grp10           VARCHAR(16)     NOT NULL,
    inhome_rate         REAL,
    svod_scrb_cnt_grp   VARCHAR(16),
    paid_chnl_cnt_grp   VARCHAR(16),
    ch_hh_avg_month1    REAL,
    kids_use_pv_month1  REAL,
    nfx_use_yn          BOOLEAN,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    last_active_at      TIMESTAMPTZ     DEFAULT NOW()
);


-- =============================================================
-- 3. vod 테이블
--    PK: full_asset_id
--    RAG 추적 컬럼 포함 (rag_processed, rag_source, rag_processed_at)
--    updated_at: 트리거로 자동 갱신
-- =============================================================

CREATE TABLE vod (
    full_asset_id       VARCHAR(64)     PRIMARY KEY,
    asset_nm            VARCHAR(255)    NOT NULL,
    ct_cl               VARCHAR(32)     NOT NULL,
    disp_rtm            VARCHAR(8),
    disp_rtm_sec        INTEGER         NOT NULL,
    genre               VARCHAR(64),
    director            VARCHAR(255),
    asset_prod          VARCHAR(64),
    smry                TEXT,
    provider            VARCHAR(128),
    genre_detail        VARCHAR(255),
    series_nm           VARCHAR(255),
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW(),
    rag_processed       BOOLEAN         DEFAULT FALSE,
    rag_source          VARCHAR(64),
    rag_processed_at    TIMESTAMPTZ,
    rag_confidence      REAL,

    -- Poster_Collection 파이프라인이 채우는 포스터 경로
    -- VPC 업로드 후 경로 또는 URL. NULL = 미수집.
    poster_url          TEXT
);


-- =============================================================
-- 4. watch_history 테이블
--    PK: watch_history_id (GENERATED ALWAYS AS IDENTITY)
--    FK: user_id_fk → "user".sha2_hash
--    FK: vod_id_fk  → vod.full_asset_id
-- =============================================================

CREATE TABLE watch_history (
    watch_history_id    BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk          VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash),
    vod_id_fk           VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id),
    strt_dt             TIMESTAMPTZ     NOT NULL,
    use_tms             REAL            NOT NULL,
    completion_rate     REAL,
    satisfaction        REAL,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),

    -- 복합 유니크: 동일 사용자가 동일 VOD를 같은 시각에 2건 기록 방지
    CONSTRAINT uq_wh_user_vod_strt UNIQUE (user_id_fk, vod_id_fk, strt_dt),

    -- CHECK 제약
    CONSTRAINT chk_wh_use_tms         CHECK (use_tms >= 0),
    CONSTRAINT chk_wh_completion_rate CHECK (completion_rate >= 0 AND completion_rate <= 1),
    CONSTRAINT chk_wh_satisfaction    CHECK (satisfaction >= 0 AND satisfaction <= 1)
);


-- =============================================================
-- 5. updated_at 자동 갱신 트리거 함수
--    재사용 가능한 범용 함수 (다른 테이블에도 적용 가능)
-- =============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- =============================================================
-- 6. vod 테이블에 트리거 적용
--    BEFORE UPDATE: UPDATE 실행 전 updated_at을 현재 시각으로 갱신
-- =============================================================

CREATE TRIGGER trg_vod_updated_at
    BEFORE UPDATE ON vod
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();


-- =============================================================
-- 7. 테이블/컬럼 COMMENT
-- =============================================================

-- "user" 테이블
COMMENT ON TABLE "user" IS
    'VOD 서비스 사용자 테이블. PK는 SHA-2 해시된 사용자 식별자.';

COMMENT ON COLUMN "user".sha2_hash           IS 'SHA-2 해시된 사용자 고유 식별자 (원본 개인정보 비식별화)';
COMMENT ON COLUMN "user".age_grp10           IS '연령대 10년 단위 (예: 20대, 30대, ..., 90대이상)';
COMMENT ON COLUMN "user".inhome_rate         IS '집 내 시청 비율 (0.0~100.0)';
COMMENT ON COLUMN "user".svod_scrb_cnt_grp   IS 'SVOD 구독 수 그룹 (예: 0건, 1건)';
COMMENT ON COLUMN "user".paid_chnl_cnt_grp   IS '유료 채널 수 그룹 (예: 0건, 1건)';
COMMENT ON COLUMN "user".ch_hh_avg_month1    IS '최근 1개월 TV 채널 월평균 시청 시간';
COMMENT ON COLUMN "user".kids_use_pv_month1  IS '최근 1개월 키즈 콘텐츠 이용 PV';
COMMENT ON COLUMN "user".nfx_use_yn          IS 'Netflix 사용 여부 (TRUE/FALSE)';
COMMENT ON COLUMN "user".created_at          IS '레코드 생성 시각 (UTC)';
COMMENT ON COLUMN "user".last_active_at      IS '마지막 활동 시각 (UTC)';

-- vod 테이블
COMMENT ON TABLE vod IS
    'VOD 콘텐츠 테이블. RAG 처리 추적 컬럼 포함. updated_at은 트리거로 자동 갱신.';

COMMENT ON COLUMN vod.full_asset_id     IS 'VOD 고유 식별자 (원본 full_asset_id)';
COMMENT ON COLUMN vod.asset_nm          IS 'VOD 콘텐츠명';
COMMENT ON COLUMN vod.ct_cl             IS '콘텐츠 대분류 (예: 영화, 라이프, 키즈)';
COMMENT ON COLUMN vod.disp_rtm         IS '표시 상영시간 원본값 (HH:MM 형식)';
COMMENT ON COLUMN vod.disp_rtm_sec     IS '상영시간 초 단위 변환값 (마이그레이션 시 계산)';
COMMENT ON COLUMN vod.genre             IS '장르';
COMMENT ON COLUMN vod.director          IS '감독명 (NULL 허용 - RAG로 보완 예정, 약 313건 누락)';
COMMENT ON COLUMN vod.asset_prod        IS '제작사/배급사';
COMMENT ON COLUMN vod.smry              IS '작품 줄거리 (NULL 허용 - RAG로 보완 예정, 약 28건 누락)';
COMMENT ON COLUMN vod.provider          IS '콘텐츠 제공사';
COMMENT ON COLUMN vod.genre_detail      IS '세부 장르';
COMMENT ON COLUMN vod.series_nm         IS '시리즈명 (NULL 허용 - 단편/독립작품은 NULL)';
COMMENT ON COLUMN vod.created_at        IS '레코드 생성 시각 (UTC)';
COMMENT ON COLUMN vod.updated_at        IS '레코드 최종 수정 시각 (UTC, trg_vod_updated_at 트리거로 자동 갱신)';
COMMENT ON COLUMN vod.rag_processed     IS 'RAG 처리 완료 여부 (FALSE: 미처리, TRUE: 처리완료)';
COMMENT ON COLUMN vod.rag_source        IS 'RAG 데이터 출처 (예: IMDB, Wiki, KMRB)';
COMMENT ON COLUMN vod.rag_processed_at  IS 'RAG 처리 완료 시각 (UTC)';
COMMENT ON COLUMN vod.rag_confidence    IS 'RAG 결과 신뢰도 (0.0~1.0). 소스별 가중치 합산 점수.';

-- watch_history 테이블
COMMENT ON TABLE watch_history IS
    '시청 이력 테이블. 사용자-VOD 시청 이벤트 단위 기록. 3,992,530건 예상.';

COMMENT ON COLUMN watch_history.watch_history_id IS '자동 생성 시청이력 고유 ID (GENERATED ALWAYS AS IDENTITY)';
COMMENT ON COLUMN watch_history.user_id_fk       IS '사용자 FK → "user".sha2_hash';
COMMENT ON COLUMN watch_history.vod_id_fk        IS 'VOD FK → vod.full_asset_id';
COMMENT ON COLUMN watch_history.strt_dt          IS '시청 시작 시각 (UTC, TIMESTAMPTZ)';
COMMENT ON COLUMN watch_history.use_tms          IS '실제 시청 시간 (초 단위, >= 0)';
COMMENT ON COLUMN watch_history.completion_rate  IS '완주율 (0.0~1.0, use_tms / disp_rtm_sec)';
COMMENT ON COLUMN watch_history.satisfaction     IS '베이지안 스코어 기반 만족도 (0.0~1.0)';
COMMENT ON COLUMN watch_history.created_at       IS '레코드 삽입 시각 (UTC)';
