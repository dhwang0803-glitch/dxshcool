-- =============================================================
-- 마이그레이션: series_nm 시즌 정보 갱신
-- 파일: Database_Design/migrations/20260320_series_nm_season_update.sql
-- 작성일: 2026-03-20
-- 배경:
--   Frontend 연동을 위해 series_nm을 시리즈 식별자로 사용.
--   asset_nm에 시즌 정보(시즌N)가 있으나 series_nm에는 미반영된 VOD 6,084건을
--   시즌별로 분리하여 series_nm을 갱신한다.
--   예: series_nm='라바', asset_nm='라바 시즌1 01회' → series_nm='라바 시즌1'
-- 영향 브랜치: API_Server(읽기), Poster_Collection(쓰기)
-- =============================================================

-- UP: series_nm에 시즌 정보 반영
-- 규칙:
--   1. 기본: asset_nm에서 '~시즌N'까지 추출
--   2. 약칭 예외: series_nm + ' 시즌N' (series_nm이 정식명이고 asset_nm이 약칭인 경우)
--   3. 제외: 메타데이터 오류 시리즈 ('가족어린이', '애니메이션')
UPDATE vod
SET series_nm = CASE
      WHEN series_nm = '패키지로 세계일주 - 뭉쳐야 뜬다'
        THEN series_nm || ' 시즌' || (regexp_match(asset_nm, '시즌\s*([0-9]+)'))[1]
      ELSE (regexp_match(asset_nm, '^(.*?시즌\s*[0-9]+)'))[1]
    END,
    updated_at = NOW()
WHERE asset_nm ~ '시즌\s*[0-9]+'
  AND series_nm !~ '시즌'
  AND series_nm NOT IN ('가족어린이', '애니메이션');
-- 예상 영향: 6,084건 UPDATE, 149개 시리즈 → 347개 시즌별 시리즈로 분리

-- DOWN: 시즌 접미사 제거 (롤백용)
-- 주의: asset_nm 기반 추출로 갱신된 경우 원본 series_nm 복원이 불완전할 수 있음
-- 완전한 롤백이 필요하면 백업 테이블에서 복원할 것
-- ROLLBACK 예시:
-- UPDATE vod
-- SET series_nm = regexp_replace(series_nm, '\s*시즌\s*[0-9]+$', ''),
--     updated_at = NOW()
-- WHERE series_nm ~ '시즌\s*[0-9]+$'
--   AND updated_at >= '2026-03-20';
