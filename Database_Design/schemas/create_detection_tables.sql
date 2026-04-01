-- =============================================================
-- 탐지 결과 테이블 DDL (3종)
-- 파일: Database_Design/schemas/create_detection_tables.sql
-- 목적: YOLO/CLIP/STT 3종 탐지 결과 저장 (Silver 계층)
-- 작성일: 2026-03-18
-- 소비 브랜치: Object_Detection(쓰기), Shopping_Ad(읽기)
-- =============================================================
-- 실행 방법: psql -U <user> -d <dbname> -f create_detection_tables.sql
-- 주의: create_tables.sql 이후에 실행 (vod 테이블 FK 참조)
-- =============================================================


-- =============================================================
-- 1. detected_object_yolo — YOLO bbox 탐지 결과
--    write-once 배치 적재 (updated_at 없음)
-- =============================================================

CREATE TABLE detected_object_yolo (
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

CREATE INDEX idx_det_yolo_vod_ts  ON detected_object_yolo(vod_id_fk, frame_ts);
CREATE INDEX idx_det_yolo_label   ON detected_object_yolo(label);

COMMENT ON TABLE detected_object_yolo IS
    'YOLO bbox 탐지 결과. Object_Detection 배치 파이프라인이 적재. write-once.';
COMMENT ON COLUMN detected_object_yolo.detected_yolo_id IS '자동 생성 PK';
COMMENT ON COLUMN detected_object_yolo.vod_id_fk        IS 'FK → vod.full_asset_id (ON DELETE CASCADE)';
COMMENT ON COLUMN detected_object_yolo.frame_ts          IS '프레임 타임스탬프 (초 단위)';
COMMENT ON COLUMN detected_object_yolo.label             IS 'YOLO COCO 클래스명 (예: person, food, car)';
COMMENT ON COLUMN detected_object_yolo.confidence        IS '탐지 신뢰도 (0.0~1.0)';
COMMENT ON COLUMN detected_object_yolo.bbox              IS 'Bounding box [x1,y1,x2,y2] 픽셀 좌표';
COMMENT ON COLUMN detected_object_yolo.created_at        IS '레코드 생성 시각 (UTC)';


-- =============================================================
-- 2. detected_object_clip — CLIP zero-shot 개념 태깅
-- =============================================================

CREATE TABLE detected_object_clip (
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

CREATE INDEX idx_det_clip_vod_ts      ON detected_object_clip(vod_id_fk, frame_ts);
CREATE INDEX idx_det_clip_category    ON detected_object_clip(ad_category);
CREATE INDEX idx_det_clip_valid       ON detected_object_clip(vod_id_fk, frame_ts)
    WHERE context_valid = TRUE;

COMMENT ON TABLE detected_object_clip IS
    'CLIP zero-shot 개념 태깅 결과. ad_category별 광고 매칭 입력. write-once.';
COMMENT ON COLUMN detected_object_clip.detected_clip_id IS '자동 생성 PK';
COMMENT ON COLUMN detected_object_clip.vod_id_fk        IS 'FK → vod.full_asset_id (ON DELETE CASCADE)';
COMMENT ON COLUMN detected_object_clip.frame_ts          IS '프레임 타임스탬프 (초 단위)';
COMMENT ON COLUMN detected_object_clip.concept           IS 'CLIP 쿼리 텍스트 (예: 한식 요리, 해변 풍경)';
COMMENT ON COLUMN detected_object_clip.clip_score        IS 'CLIP 유사도 점수 (0.0~1.0)';
COMMENT ON COLUMN detected_object_clip.ad_category       IS '광고 카테고리 (한식, 지방특산물, 여행지 등)';
COMMENT ON COLUMN detected_object_clip.context_valid     IS 'context_filter 검증 통과 여부';
COMMENT ON COLUMN detected_object_clip.context_reason    IS 'context_filter 실패 사유 (valid=TRUE이면 NULL)';
COMMENT ON COLUMN detected_object_clip.created_at        IS '레코드 생성 시각 (UTC)';


-- =============================================================
-- 3. detected_object_stt — Whisper STT 키워드 추출
-- =============================================================

CREATE TABLE detected_object_stt (
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

CREATE INDEX idx_det_stt_vod_ts       ON detected_object_stt(vod_id_fk, start_ts, end_ts);
CREATE INDEX idx_det_stt_category     ON detected_object_stt(ad_category);
CREATE INDEX idx_det_stt_keyword      ON detected_object_stt(keyword);

COMMENT ON TABLE detected_object_stt IS
    'Whisper STT 키워드 추출 결과. 구간(start_ts~end_ts) 단위. write-once.';
COMMENT ON COLUMN detected_object_stt.detected_stt_id IS '자동 생성 PK';
COMMENT ON COLUMN detected_object_stt.vod_id_fk       IS 'FK → vod.full_asset_id (ON DELETE CASCADE)';
COMMENT ON COLUMN detected_object_stt.start_ts         IS '구간 시작 타임스탬프 (초)';
COMMENT ON COLUMN detected_object_stt.end_ts           IS '구간 종료 타임스탬프 (초), >= start_ts';
COMMENT ON COLUMN detected_object_stt.transcript       IS '전체 전사 텍스트';
COMMENT ON COLUMN detected_object_stt.keyword          IS '매칭된 키워드';
COMMENT ON COLUMN detected_object_stt.ad_category      IS '광고 카테고리 (한식, 지방특산물, 여행지 등)';
COMMENT ON COLUMN detected_object_stt.ad_hints         IS 'JSON 배열 문자열 (지역 힌트 등)';
COMMENT ON COLUMN detected_object_stt.created_at       IS '레코드 생성 시각 (UTC)';
