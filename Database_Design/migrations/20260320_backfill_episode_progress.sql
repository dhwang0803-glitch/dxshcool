-- =============================================================
-- 마이그레이션: episode_progress 초기 데이터 적재
-- 파일: Database_Design/migrations/20260320_backfill_episode_progress.sql
-- 작성일: 2026-03-20
-- 배경:
--   watch_history(ML 전용)에서 에피소드별 최신 시청 기록을 추출하여
--   episode_progress에 사전 연산 적재. API 응답은 이 테이블만 사용.
--   연산식: ROUND(use_tms / disp_rtm_sec * 100), 상한 100 캡핑.
-- 전제:
--   20260320_add_user_activity_tables.sql 실행 후 적용
-- 예상 적재: ~2,369,154건
-- 예상 소요: 대용량 INSERT — 수 분 소요 가능
-- 영향 브랜치: API_Server(읽기)
-- =============================================================

-- UP: watch_history → episode_progress 사전 연산 적재
-- 규칙:
--   1. 유저×에피소드 DISTINCT: 동일 유저가 같은 에피소드를 여러 번 시청한 경우 최신 기록만
--   2. completion_rate = ROUND(use_tms / disp_rtm_sec * 100), 상한 100 캡핑
--   3. disp_rtm_sec NULL/0인 VOD 제외 (연산 불가)
--   4. series_nm NULL인 VOD 제외 (그룹핑 불가)

INSERT INTO public.episode_progress
    (user_id_fk, vod_id_fk, series_nm, completion_rate, watched_at)
SELECT DISTINCT ON (wh.user_id_fk, wh.vod_id_fk)
    wh.user_id_fk,
    wh.vod_id_fk,
    v.series_nm,
    LEAST(ROUND(wh.use_tms / v.disp_rtm_sec * 100)::SMALLINT, 100::SMALLINT),
    wh.strt_dt
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE v.disp_rtm_sec > 0
  AND v.series_nm IS NOT NULL
ORDER BY wh.user_id_fk, wh.vod_id_fk, wh.strt_dt DESC;

-- DOWN: 롤백
-- TRUNCATE public.episode_progress;
