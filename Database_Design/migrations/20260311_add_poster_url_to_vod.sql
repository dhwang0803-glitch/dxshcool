-- =============================================================
-- Migration: add poster_url to vod table
-- Date: 2026-03-11
-- Branch: Poster_Collection
-- Purpose: Naver에서 수집한 시리즈 포스터 이미지 경로(VPC 업로드 후 경로) 저장
--
-- 관련 브랜치: Poster_Collection
--   - crawl_posters.py  → 포스터 이미지 수집·로컬 저장
--   - export_manifest.py → Google Drive 전달용 매니페스트 생성
--   - update_poster_url.py → 이 컬럼에 VPC 경로 적재 (DB 관리자 실행)
--
-- 주의: 동일 시리즈의 모든 에피소드(같은 series_nm)는 같은 poster_url 값을 가진다.
--       Poster_Collection 파이프라인은 series_nm 기준으로 UPDATE한다.
--
-- 실행 방법:
--   set -a && source .env && set +a
--   PGPASSWORD=$DB_PASSWORD psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME \
--     -f Database_Design/migrations/20260311_add_poster_url_to_vod.sql
-- =============================================================

BEGIN;

-- [1] poster_url 컬럼 추가
--     TEXT: 경로 길이 제한 없이 허용 (VPC 절대 경로 또는 URL)
ALTER TABLE vod
    ADD COLUMN IF NOT EXISTS poster_url TEXT;

COMMENT ON COLUMN vod.poster_url IS
    'VPC에 저장된 포스터 이미지 경로. Poster_Collection 파이프라인이 채운다. '
    'NULL = 아직 수집되지 않음.';


-- [2] series_nm 인덱스 추가
--     Poster_Collection UPDATE 시 WHERE series_nm = ? 쿼리 성능 확보
--     API_Server VOD 목록 조회 시 시리즈 필터링에도 활용
CREATE INDEX IF NOT EXISTS idx_vod_series_nm
    ON vod (series_nm);


-- [3] poster_url NULL 여부 인덱스 (부분 인덱스)
--     Poster_Collection 파이프라인이 미수집 대상을 빠르게 조회할 때 사용
--     예: SELECT DISTINCT series_nm FROM vod WHERE poster_url IS NULL
CREATE INDEX IF NOT EXISTS idx_vod_poster_url_null
    ON vod (series_nm)
    WHERE poster_url IS NULL;


COMMIT;
