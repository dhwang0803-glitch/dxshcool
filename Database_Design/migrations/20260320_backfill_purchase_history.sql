-- =============================================================
-- 마이그레이션: purchase_history 초기 데이터 적재
-- 파일: Database_Design/migrations/20260320_backfill_purchase_history.sql
-- 작성일: 2026-03-20
-- 배경:
--   watch_history에서 유료 VOD(FOD 제외) 시청 기록을 추출하여
--   유저×시리즈 단위로 구매 내역을 역추정 적재.
--   FOD(Free On Demand)는 무료 콘텐츠이므로 구매 기록 미생성.
-- 결정:
--   - FOD 제외 전부 구매 대상 (RVOD, SVOD, 제작사명 등)
--   - legacy backfill: option_type='permanent', points_used=0
--   - purchased_at = 해당 시리즈 최초 시청 시각
-- 전제:
--   20260320_add_user_activity_tables.sql 실행 후 적용
-- 예상 적재: ~897,674건
-- 예상 소요: 대용량 GROUP BY — 수 분 소요 가능
-- 영향 브랜치: API_Server(읽기)
-- =============================================================

-- UP: watch_history → purchase_history 유료 VOD 구매 역추정 적재
-- 규칙:
--   1. asset_prod = 'FOD' 제외 (무료 콘텐츠)
--   2. asset_prod IS NULL 또는 빈 문자열도 포함 (분류 불명 → 유료로 간주)
--   3. 유저×시리즈 단위 GROUP BY: 최초 시청 시각을 purchased_at으로 사용
--   4. series_nm NULL인 VOD 제외
--   5. option_type = 'permanent' (legacy 데이터는 영구 소장 처리)
--   6. points_used = 0 (실제 결제가 아닌 역추정 backfill)
--   7. expires_at = NULL (영구 소장)

INSERT INTO public.purchase_history
    (user_id_fk, series_nm, option_type, points_used, purchased_at, expires_at)
SELECT
    wh.user_id_fk,
    v.series_nm,
    'permanent',
    0,
    MIN(wh.strt_dt),
    NULL
FROM watch_history wh
JOIN vod v ON wh.vod_id_fk = v.full_asset_id
WHERE v.asset_prod IS DISTINCT FROM 'FOD'
  AND v.series_nm IS NOT NULL
GROUP BY wh.user_id_fk, v.series_nm;

-- DOWN: 롤백
-- TRUNCATE public.purchase_history;
