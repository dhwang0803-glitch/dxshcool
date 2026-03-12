-- =============================================================
-- Migration: vod_recommendation covering index 교체
-- 파일: migrations/20260312_covering_index_vod_rec.sql
-- 작성일: 2026-03-12
-- 배경:
--   기존 idx_vod_rec_user(user_id_fk, rank)은 API 반환 컬럼
--   (vod_id_fk, score, recommendation_type, expires_at)을 커버하지 않아
--   heap fetch가 발생함. 커버링 인덱스로 교체하여 heap fetch 제거.
-- 쿼리 패턴:
--   SELECT vod_id_fk, rank, score, recommendation_type
--   FROM vod_recommendation
--   WHERE user_id_fk = $1 AND expires_at > NOW()
--   ORDER BY rank LIMIT N;
-- =============================================================

BEGIN;

-- 1. 기존 인덱스 제거
DROP INDEX IF EXISTS idx_vod_rec_user;

-- 2. 커버링 인덱스 생성
--    (user_id_fk, rank): WHERE + ORDER BY 처리
--    INCLUDE: heap fetch 없이 API 응답 컬럼 모두 커버
CREATE INDEX idx_vod_rec_user_covering
    ON vod_recommendation (user_id_fk, rank)
    INCLUDE (vod_id_fk, score, recommendation_type, expires_at);

COMMIT;

-- =============================================================
-- 롤백 (필요 시)
-- =============================================================
-- BEGIN;
-- DROP INDEX IF EXISTS idx_vod_rec_user_covering;
-- CREATE INDEX idx_vod_rec_user ON vod_recommendation (user_id_fk, rank);
-- COMMIT;

-- =============================================================
-- 검증 쿼리
-- =============================================================
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE tablename = 'vod_recommendation'
-- ORDER BY indexname;
