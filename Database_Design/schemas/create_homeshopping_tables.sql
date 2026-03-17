-- =============================================================
-- 홈쇼핑 상품 테이블 DDL
-- 파일: Database_Design/schemas/create_homeshopping_tables.sql
-- 목적: 홈쇼핑 편성표 크롤링 결과 저장
-- 작성일: 2026-03-17
-- 소비 브랜치: Shopping_Ad
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_homeshopping_tables.sql
-- =============================================================

CREATE TABLE IF NOT EXISTS homeshopping_product (
    id              SERIAL PRIMARY KEY,
    channel         VARCHAR(32) NOT NULL,
    broadcast_date  DATE NOT NULL,
    start_time      TIME,
    end_time        TIME,
    raw_name        TEXT NOT NULL,
    normalized_name VARCHAR(200),
    price           INTEGER,
    product_url     TEXT,
    image_url       TEXT,
    program_name    VARCHAR(200),
    crawled_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(channel, broadcast_date, start_time, raw_name)
);

CREATE INDEX IF NOT EXISTS idx_hsp_channel_date
    ON homeshopping_product(channel, broadcast_date);

CREATE INDEX IF NOT EXISTS idx_hsp_normalized
    ON homeshopping_product(normalized_name);
