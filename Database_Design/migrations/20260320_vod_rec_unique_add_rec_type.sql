-- =============================================================
-- 마이그레이션: serving.vod_recommendation UNIQUE 제약에 recommendation_type 추가
-- 파일: Database_Design/migrations/20260320_vod_rec_unique_add_rec_type.sql
-- 날짜: 2026-03-20
-- 배경:
--   CF_Engine(COLLABORATIVE)과 Vector_Search(VISUAL_SIMILARITY)가
--   Cloud Run Jobs로 독립 실행되어 동일 user-vod 쌍을 각각 저장할 수 있음.
--   현재 UNIQUE(user_id_fk, vod_id_fk)는 타입별 공존 불가 → 한쪽이 덮어씌워짐.
--   recommendation_type을 UNIQUE에 포함하여 타입별 독립 저장 허용.
-- 영향 브랜치: CF_Engine, Vector_Search, Hybrid_Layer, API_Server
-- =============================================================

BEGIN;

-- ── 1. 기존 Partial Unique 인덱스 삭제 ──────────────────────────────

DROP INDEX IF EXISTS serving.uq_vod_rec_user_vod;
DROP INDEX IF EXISTS serving.uq_vod_rec_source_vod;

-- ── 2. recommendation_type 포함한 Partial Unique 인덱스 재생성 ──────

-- 유저 기반 추천: 동일 유저-VOD라도 CF/Vector/Hybrid 각각 별도 행 허용
CREATE UNIQUE INDEX uq_vod_rec_user_vod
    ON serving.vod_recommendation (user_id_fk, vod_id_fk, recommendation_type)
    WHERE user_id_fk IS NOT NULL;

-- 콘텐츠 기반 추천: 동일 소스VOD-VOD라도 타입별 별도 행 허용
CREATE UNIQUE INDEX uq_vod_rec_source_vod
    ON serving.vod_recommendation (source_vod_id, vod_id_fk, recommendation_type)
    WHERE source_vod_id IS NOT NULL;

COMMIT;

-- =============================================================
-- DOWN (롤백)
-- =============================================================
-- BEGIN;
-- DROP INDEX IF EXISTS serving.uq_vod_rec_user_vod;
-- DROP INDEX IF EXISTS serving.uq_vod_rec_source_vod;
--
-- CREATE UNIQUE INDEX uq_vod_rec_user_vod
--     ON serving.vod_recommendation (user_id_fk, vod_id_fk)
--     WHERE user_id_fk IS NOT NULL;
--
-- CREATE UNIQUE INDEX uq_vod_rec_source_vod
--     ON serving.vod_recommendation (source_vod_id, vod_id_fk)
--     WHERE source_vod_id IS NOT NULL;
-- COMMIT;
