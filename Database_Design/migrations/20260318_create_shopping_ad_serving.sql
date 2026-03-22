-- =============================================================
-- Migration: 광고 서빙 테이블 생성 (serving 스키마)
-- 파일: migrations/20260318_create_shopping_ad_serving.sql
-- 작성일: 2026-03-18 (마이그레이션 보완: 2026-03-21)
-- =============================================================
-- 배경:
--   VOD 재생 중 음식/관광지 인식 결과를 기반으로
--   지자체 광고 팝업 또는 제철장터 채널 연계 서빙.
--   Shopping_Ad 브랜치가 쓰고, API_Server가 읽음.
--
-- 영향받는 브랜치:
--   Shopping_Ad — 쓰기
--   API_Server  — 읽기
-- =============================================================

BEGIN;

CREATE TABLE IF NOT EXISTS serving.shopping_ad (
    shopping_ad_id      BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    ts_start            REAL            NOT NULL,
    ts_end              REAL            NOT NULL,
    ad_category         VARCHAR(32)     NOT NULL,
    signal_source       VARCHAR(16)     NOT NULL,
    score               REAL            NOT NULL,
    ad_hints            TEXT,
    ad_action_type      VARCHAR(32)     NOT NULL,
    ad_image_url        TEXT,
    product_name        VARCHAR(200),
    channel             VARCHAR(32),
    generated_at        TIMESTAMPTZ     DEFAULT NOW(),
    expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '30 days',

    CONSTRAINT chk_sa_ts_range       CHECK (ts_end >= ts_start),
    CONSTRAINT chk_sa_score          CHECK (score >= 0.0 AND score <= 1.0),
    CONSTRAINT chk_sa_signal_source  CHECK (signal_source IN ('stt', 'clip', 'yolo', 'ocr')),
    CONSTRAINT chk_sa_action_type    CHECK (ad_action_type IN ('local_gov_popup', 'seasonal_market'))
);

CREATE INDEX IF NOT EXISTS idx_sa_vod_ts       ON serving.shopping_ad(vod_id_fk, ts_start, ts_end);
CREATE INDEX IF NOT EXISTS idx_sa_expires      ON serving.shopping_ad(expires_at);
CREATE INDEX IF NOT EXISTS idx_sa_category     ON serving.shopping_ad(ad_category);
CREATE INDEX IF NOT EXISTS idx_sa_action_type  ON serving.shopping_ad(ad_action_type);

COMMENT ON TABLE serving.shopping_ad IS
    'Gold 계층: VOD 재생 중 광고 서빙 테이블. 지자체 광고 팝업 + 제철장터 채널 연계. TTL 30일.';

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- DROP TABLE IF EXISTS serving.shopping_ad;
-- COMMIT;
