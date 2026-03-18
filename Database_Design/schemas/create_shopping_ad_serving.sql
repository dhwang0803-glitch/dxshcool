-- =============================================================
-- 쇼핑 광고 서빙 테이블 DDL (Gold 계층)
-- 파일: Database_Design/schemas/create_shopping_ad_serving.sql
-- 목적: VOD 재생 중 쇼핑 팝업 실시간 서빙
-- 작성일: 2026-03-18
-- 소비 브랜치: Shopping_Ad(쓰기), API_Server(읽기)
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_shopping_ad_serving.sql
-- 주의: serving 스키마가 먼저 생성되어야 함 (20260312_create_serving_schema.sql)
--       homeshopping_product 테이블 FK 참조 (create_homeshopping_tables.sql)
-- =============================================================

CREATE TABLE serving.shopping_ad (
    shopping_ad_id      BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    ts_start            REAL            NOT NULL,
    ts_end              REAL            NOT NULL,
    ad_category         VARCHAR(32)     NOT NULL,
    signal_source       VARCHAR(16)     NOT NULL,
    score               REAL            NOT NULL,
    ad_hints            TEXT,
    product_id_fk       INTEGER         REFERENCES homeshopping_product(id) ON DELETE SET NULL,
    product_name        VARCHAR(200),
    product_price       INTEGER,
    product_url         TEXT,
    image_url           TEXT,
    channel             VARCHAR(32),
    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '30 days',

    CONSTRAINT chk_sa_ts_range      CHECK (ts_end >= ts_start),
    CONSTRAINT chk_sa_score         CHECK (score >= 0.0 AND score <= 1.0),
    CONSTRAINT chk_sa_signal_source CHECK (signal_source IN ('stt', 'clip', 'yolo'))
);

-- API 쿼리 패턴: WHERE vod_id_fk=$1 AND ts_start <= $2 AND ts_end >= $2
CREATE INDEX idx_sa_vod_ts       ON serving.shopping_ad(vod_id_fk, ts_start, ts_end);
CREATE INDEX idx_sa_expires      ON serving.shopping_ad(expires_at);
CREATE INDEX idx_sa_category     ON serving.shopping_ad(ad_category);

COMMENT ON TABLE serving.shopping_ad IS
    'Gold 계층: VOD 재생 중 쇼핑 팝업 서빙 테이블. 상품 정보 비정규화 (JOIN 없이 응답). TTL 30일.';
COMMENT ON COLUMN serving.shopping_ad.shopping_ad_id IS '자동 생성 PK';
COMMENT ON COLUMN serving.shopping_ad.vod_id_fk      IS 'FK → vod.full_asset_id (ON DELETE CASCADE)';
COMMENT ON COLUMN serving.shopping_ad.ts_start        IS '트리거 구간 시작 (초)';
COMMENT ON COLUMN serving.shopping_ad.ts_end          IS '트리거 구간 종료 (초), >= ts_start';
COMMENT ON COLUMN serving.shopping_ad.ad_category     IS '광고 카테고리 (한식, 지방특산물, 여행지 등)';
COMMENT ON COLUMN serving.shopping_ad.signal_source   IS '탐지 소스 (stt/clip/yolo)';
COMMENT ON COLUMN serving.shopping_ad.score           IS '매칭 신뢰도 (0.0~1.0)';
COMMENT ON COLUMN serving.shopping_ad.ad_hints        IS 'JSON 배열 (지역 힌트 등)';
COMMENT ON COLUMN serving.shopping_ad.product_id_fk   IS 'FK → homeshopping_product.id (ON DELETE SET NULL)';
COMMENT ON COLUMN serving.shopping_ad.product_name    IS '비정규화: 상품명';
COMMENT ON COLUMN serving.shopping_ad.product_price   IS '비정규화: 판매가';
COMMENT ON COLUMN serving.shopping_ad.product_url     IS '비정규화: 상품 URL';
COMMENT ON COLUMN serving.shopping_ad.image_url       IS '비정규화: 상품 이미지 URL';
COMMENT ON COLUMN serving.shopping_ad.channel         IS '홈쇼핑 채널명 (예: CJ온스타일)';
COMMENT ON COLUMN serving.shopping_ad.generated_at    IS '레코드 생성 시각 (UTC)';
COMMENT ON COLUMN serving.shopping_ad.expires_at      IS 'TTL 만료 시각 (기본 30일 후)';
