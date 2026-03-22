-- =============================================================
-- Migration: YOLO/CLIP/STT 탐지 결과 테이블 3종 생성
-- 파일: migrations/20260318_create_detection_tables.sql
-- 작성일: 2026-03-18 (마이그레이션 보완: 2026-03-21)
-- =============================================================
-- 배경:
--   Object_Detection 파이프라인이 VOD 영상에서 탐지한
--   음식/관광지 객체(YOLO), 개념 태그(CLIP), 키워드(STT)를 저장.
--   Shopping_Ad 브랜치가 읽어서 광고 매칭에 사용.
--
-- 영향받는 브랜치:
--   Object_Detection — 쓰기
--   Shopping_Ad      — 읽기
-- =============================================================

BEGIN;

-- 1. detected_object_yolo
CREATE TABLE IF NOT EXISTS detected_object_yolo (
    detected_yolo_id    BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    frame_ts            REAL            NOT NULL,
    label               VARCHAR(64)     NOT NULL,
    confidence          REAL            NOT NULL,
    bbox                REAL[]          NOT NULL,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),

    CONSTRAINT chk_yolo_confidence CHECK (confidence >= 0.0 AND confidence <= 1.0),
    CONSTRAINT chk_yolo_bbox_len   CHECK (array_length(bbox, 1) = 4)
);

CREATE INDEX IF NOT EXISTS idx_det_yolo_vod_ts  ON detected_object_yolo(vod_id_fk, frame_ts);
CREATE INDEX IF NOT EXISTS idx_det_yolo_label   ON detected_object_yolo(label);

COMMENT ON TABLE detected_object_yolo IS
    'YOLO bbox 탐지 결과. Object_Detection 배치 파이프라인이 적재. write-once.';

-- 2. detected_object_clip
CREATE TABLE IF NOT EXISTS detected_object_clip (
    detected_clip_id    BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    frame_ts            REAL            NOT NULL,
    concept             VARCHAR(200)    NOT NULL,
    clip_score          REAL            NOT NULL,
    ad_category         VARCHAR(32)     NOT NULL,
    context_valid       BOOLEAN         NOT NULL DEFAULT TRUE,
    context_reason      TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),

    CONSTRAINT chk_clip_score CHECK (clip_score >= 0.0 AND clip_score <= 1.0)
);

CREATE INDEX IF NOT EXISTS idx_det_clip_vod_ts   ON detected_object_clip(vod_id_fk, frame_ts);
CREATE INDEX IF NOT EXISTS idx_det_clip_category ON detected_object_clip(ad_category);
CREATE INDEX IF NOT EXISTS idx_det_clip_valid    ON detected_object_clip(vod_id_fk, frame_ts)
    WHERE context_valid = TRUE;

COMMENT ON TABLE detected_object_clip IS
    'CLIP zero-shot 개념 태깅 결과. ad_category별 광고 매칭 입력. write-once.';

-- 3. detected_object_stt
CREATE TABLE IF NOT EXISTS detected_object_stt (
    detected_stt_id     BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    vod_id_fk           VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    start_ts            REAL            NOT NULL,
    end_ts              REAL            NOT NULL,
    transcript          TEXT,
    keyword             VARCHAR(100)    NOT NULL,
    ad_category         VARCHAR(32)     NOT NULL,
    ad_hints            TEXT,
    created_at          TIMESTAMPTZ     DEFAULT NOW(),

    CONSTRAINT chk_stt_ts_range CHECK (end_ts >= start_ts)
);

CREATE INDEX IF NOT EXISTS idx_det_stt_vod_ts   ON detected_object_stt(vod_id_fk, start_ts, end_ts);
CREATE INDEX IF NOT EXISTS idx_det_stt_category ON detected_object_stt(ad_category);
CREATE INDEX IF NOT EXISTS idx_det_stt_keyword  ON detected_object_stt(keyword);

COMMENT ON TABLE detected_object_stt IS
    'Whisper STT 키워드 추출 결과. 구간(start_ts~end_ts) 단위. write-once.';

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- DROP TABLE IF EXISTS detected_object_stt;
-- DROP TABLE IF EXISTS detected_object_clip;
-- DROP TABLE IF EXISTS detected_object_yolo;
-- COMMIT;
