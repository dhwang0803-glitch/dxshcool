-- =============================================================
-- 제철장터 편성 테이블 DDL
-- 파일: Database_Design/schemas/create_homeshopping_tables.sql
-- 목적: 제철장터 채널 편성표 저장 (음식 인식 시 채널 연계용)
-- 작성일: 2026-03-17 (2026-03-19 재설계: 홈쇼핑 → 제철장터)
-- 소비 브랜치: Shopping_Ad
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_homeshopping_tables.sql
-- =============================================================

CREATE TABLE IF NOT EXISTS seasonal_market (
    id              SERIAL PRIMARY KEY,
    product_name    VARCHAR(200) NOT NULL,
    broadcast_date  DATE NOT NULL,
    start_time      TIME NOT NULL,
    end_time        TIME,
    channel         VARCHAR(32) NOT NULL DEFAULT '제철장터',
    crawled_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel, broadcast_date, start_time, product_name)
);

CREATE INDEX IF NOT EXISTS idx_sm_date_time
    ON seasonal_market(broadcast_date, start_time, end_time);

CREATE INDEX IF NOT EXISTS idx_sm_product
    ON seasonal_market(product_name);

COMMENT ON TABLE seasonal_market IS
    '제철장터 채널 편성표. 음식 인식 시 현재 방송 중인 상품과 매칭하여 채널 이동 안내.';
COMMENT ON COLUMN seasonal_market.id             IS '자동 생성 PK';
COMMENT ON COLUMN seasonal_market.product_name   IS '방송 상품명 (크롤링 수집)';
COMMENT ON COLUMN seasonal_market.broadcast_date IS '방송 날짜';
COMMENT ON COLUMN seasonal_market.start_time     IS '방송 시작 시각';
COMMENT ON COLUMN seasonal_market.end_time       IS '방송 종료 시각';
COMMENT ON COLUMN seasonal_market.channel        IS '채널명 (기본: 제철장터)';
COMMENT ON COLUMN seasonal_market.crawled_at     IS '크롤링 수집 시각 (UTC)';
