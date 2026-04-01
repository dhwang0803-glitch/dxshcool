-- =============================================================
-- 마이그레이션: series_nm 커버링 인덱스 추가
-- 파일: Database_Design/migrations/20260320_add_covering_index_series_nm.sql
-- 작성일: 2026-03-20
-- 배경:
--   API_Server에서 series_nm 기준으로 시리즈 상세/홈 섹션 조회 시
--   인덱스 온리 스캔이 가능하도록 커버링 인덱스 추가.
--   기존 idx_vod_series_nm (단순 B-tree)에 추가로 생성.
-- 영향 브랜치: API_Server(읽기)
-- =============================================================

-- UP: 커버링 인덱스 추가
CREATE INDEX IF NOT EXISTS idx_vod_series_nm_cover
    ON public.vod (series_nm)
    INCLUDE (full_asset_id, asset_nm, ct_cl, poster_url);

-- DOWN: 롤백
-- DROP INDEX IF EXISTS idx_vod_series_nm_cover;
