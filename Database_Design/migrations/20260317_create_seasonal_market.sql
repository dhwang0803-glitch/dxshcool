-- =============================================================
-- Migration: 제철장터 편성 테이블 생성
-- 파일: migrations/20260317_create_seasonal_market.sql
-- 작성일: 2026-03-17 (마이그레이션 보완: 2026-03-21)
-- =============================================================
-- 배경:
--   Shopping_Ad 브랜치가 음식 인식 시 제철장터 채널 편성표와 매칭하여
--   채널 이동/시청예약 안내를 제공하기 위한 편성 데이터 저장.
--
-- 영향받는 브랜치:
--   Shopping_Ad — 읽기/쓰기
-- =============================================================

BEGIN;

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

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- DROP TABLE IF EXISTS seasonal_market;
-- COMMIT;
