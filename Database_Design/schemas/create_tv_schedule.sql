-- =============================================================
-- EPG 방송 편성표 테이블 DDL
-- 파일: Database_Design/schemas/create_tv_schedule.sql
-- 목적: TV 실시간 시간표 (EPG) 저장
-- 작성일: 2026-03-18
-- 소비 브랜치: Shopping_Ad(읽기)
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_tv_schedule.sql
-- =============================================================

CREATE TABLE tv_schedule (
    tv_schedule_id      BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    channel             VARCHAR(64)     NOT NULL,
    broadcast_date      DATE            NOT NULL,
    start_time          TIME            NOT NULL,
    end_time            TIME,
    program_name        VARCHAR(300)    NOT NULL,
    genre               VARCHAR(64),
    is_live             BOOLEAN         DEFAULT FALSE,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     DEFAULT NOW(),

    CONSTRAINT uq_tv_schedule UNIQUE (channel, broadcast_date, start_time)
);

CREATE INDEX idx_tv_sched_channel_date ON tv_schedule(channel, broadcast_date);
CREATE INDEX idx_tv_sched_time_range   ON tv_schedule(broadcast_date, start_time, end_time);

-- updated_at 자동 갱신 트리거 (update_updated_at_column 함수는 create_tables.sql에서 생성됨)
CREATE TRIGGER trg_tv_schedule_updated_at
    BEFORE UPDATE ON tv_schedule
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

COMMENT ON TABLE tv_schedule IS
    'EPG 방송 편성표. 외부 EPG 소스에서 적재. Shopping_Ad가 홈쇼핑 시간대 매칭에 사용.';
COMMENT ON COLUMN tv_schedule.tv_schedule_id  IS '자동 생성 PK';
COMMENT ON COLUMN tv_schedule.channel         IS '채널명 (예: CJ온스타일, 현대홈쇼핑)';
COMMENT ON COLUMN tv_schedule.broadcast_date  IS '방송일';
COMMENT ON COLUMN tv_schedule.start_time      IS '방송 시작 시각';
COMMENT ON COLUMN tv_schedule.end_time        IS '방송 종료 시각 (NULL 허용)';
COMMENT ON COLUMN tv_schedule.program_name    IS '프로그램명';
COMMENT ON COLUMN tv_schedule.genre           IS '장르 (예: 홈쇼핑, 뉴스)';
COMMENT ON COLUMN tv_schedule.is_live         IS '실시간 방송 여부';
COMMENT ON COLUMN tv_schedule.created_at      IS '레코드 생성 시각 (UTC)';
COMMENT ON COLUMN tv_schedule.updated_at      IS '최종 수정 시각 (UTC, 트리거 자동 갱신)';
