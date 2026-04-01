-- ============================================================
-- rec_sentence 테이블 세그먼트 기반 재설계 + user_segment 신규
-- ============================================================
-- 배경: gen_rec_sentence 브랜치가 K-Means(k=5) 세그먼트 기반으로
--       rec_sentence를 생성하도록 변경됨.
--       기존 DDL은 user_id_fk 기반(유저별 문구)이었으나,
--       실제 운영 DB는 segment_id 기반(세그먼트별 문구)으로 구성.
--       이 마이그레이션은 DDL을 실제 DB 상태에 일치시킨다.
--
-- 변경 사항:
--   1. serving.rec_sentence: user_id_fk 기반 → segment_id 기반 PK 전환
--   2. public.user_segment: 신규 테이블 (K-Means 클러스터 결과)
--
-- 실제 DB 상태 (2026-04-01 확인):
--   serving.rec_sentence: 66,223건 (PK: vod_id_fk, segment_id)
--   public.user_segment:  33,600건 (PK: user_id_fk)
-- ============================================================

-- UP

-- 1. user_segment 테이블 (이미 존재하면 스킵)
CREATE TABLE IF NOT EXISTS public.user_segment (
    user_id_fk   VARCHAR(64) NOT NULL PRIMARY KEY,
    segment_id   SMALLINT    NOT NULL,
    assigned_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE public.user_segment IS 'K-Means(k=5) 유저 세그먼트 — gen_rec_sentence 생성, API_Server 소비';

-- 2. rec_sentence 재설계 (이미 변경된 상태면 스킵)
-- 기존 테이블 존재 시 DROP → CREATE (데이터 재적재 필요)
-- 주의: 운영 DB에서는 이미 segment_id 기반으로 전환 완료.
--       이 마이그레이션은 DDL 문서화 용도.

-- DROP TABLE IF EXISTS serving.rec_sentence;

CREATE TABLE IF NOT EXISTS serving.rec_sentence (
    vod_id_fk    VARCHAR(64) NOT NULL,
    segment_id   SMALLINT    NOT NULL,
    rec_sentence TEXT        NOT NULL,
    model_name   VARCHAR(100),
    generated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT rec_sentence_pkey PRIMARY KEY (vod_id_fk, segment_id)
);

COMMENT ON TABLE serving.rec_sentence IS '세그먼트별 VOD 추천 문구 — gen_rec_sentence 생성, API_Server 소비';

-- DOWN (롤백용 — 구 스키마 복원 시)
-- DROP TABLE IF EXISTS serving.rec_sentence;
-- CREATE TABLE serving.rec_sentence (
--     rec_sentence_id  SERIAL PRIMARY KEY,
--     user_id_fk       VARCHAR(64) NOT NULL REFERENCES public."user"(sha2_hash) ON DELETE CASCADE,
--     vod_id_fk        VARCHAR(64) NOT NULL REFERENCES public.vod(full_asset_id) ON DELETE CASCADE,
--     rec_reason       TEXT NOT NULL,
--     rec_sentence     TEXT NOT NULL,
--     generated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
--     expires_at       TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),
--     CONSTRAINT uq_rec_sentence_user_vod UNIQUE (user_id_fk, vod_id_fk)
-- );
-- DROP TABLE IF EXISTS public.user_segment;
