-- =============================================================
-- 마이그레이션: ct_cl 값 통일 — "TV 드라마" → "TV드라마"
-- 파일: migrations/20260319_unify_ct_cl_tv_drama.sql
-- 작성일: 2026-03-19
-- 목적: 공백 포함 "TV 드라마"를 공백 없는 "TV드라마"로 통일
-- =============================================================

-- ─── 사전 확인 ───
-- 영향 건수 확인 (실행 전 dry-run)
SELECT ct_cl, COUNT(*) AS cnt
  FROM vod
 WHERE ct_cl IN ('TV드라마', 'TV 드라마')
 GROUP BY ct_cl
 ORDER BY ct_cl;

-- ─── UP: 통일 ───
BEGIN;

UPDATE vod
   SET ct_cl = 'TV드라마'
 WHERE ct_cl = 'TV 드라마';

-- 결과 검증: "TV 드라마" 잔존 건수 = 0 이어야 함
DO $$
DECLARE
    v_remaining INT;
BEGIN
    SELECT COUNT(*) INTO v_remaining
      FROM vod
     WHERE ct_cl = 'TV 드라마';

    IF v_remaining > 0 THEN
        RAISE EXCEPTION '[FAIL] "TV 드라마" 잔존 %건 — 롤백', v_remaining;
    END IF;

    RAISE NOTICE '[PASS] "TV 드라마" → "TV드라마" 통일 완료 (잔존 0건)';
END $$;

COMMIT;

-- ─── DOWN: 롤백 (필요 시) ───
-- 원본 CSV에서 어떤 값이었는지 복구 불가하므로,
-- 롤백이 필요하면 아래를 수동 실행:
-- UPDATE vod SET ct_cl = 'TV 드라마' WHERE ct_cl = 'TV드라마';
-- 단, 원래 "TV드라마"였던 건과 구분 불가함에 유의.
