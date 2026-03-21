-- =============================================================
-- 마이그레이션: user.point_balance 캐시 컬럼 + watch_reservation 테이블
-- 날짜: 2026-03-21
-- 배경:
--   인프라 제약(1GB RAM)으로 Redis 미도입.
--   방안 A(PG 내장 기능 + 인메모리 버퍼) 채택에 따라:
--   1) point_balance를 user 테이블 캐시 컬럼으로 추가 (O(N) SUM → O(1) PK)
--   2) watch_reservation 테이블 신설 (시청예약 + 알림)
--   3) PG LISTEN/NOTIFY 트리거 추가 (마이페이지 실시간 갱신)
-- 영향 브랜치: API_Server (읽기/쓰기)
-- =============================================================


-- [1] user.point_balance 캐시 컬럼 추가
ALTER TABLE public."user"
    ADD COLUMN IF NOT EXISTS point_balance INTEGER NOT NULL DEFAULT 0;

COMMENT ON COLUMN public."user".point_balance IS
    '포인트 잔액 캐시. point_history INSERT 트리거가 자동 갱신. O(1) PK 조회.';

-- 초기값 세팅 (기존 point_history 데이터 기반)
UPDATE public."user" u
SET point_balance = COALESCE(sub.balance, 0)
FROM (
    SELECT user_id_fk,
           SUM(CASE WHEN type = 'earn' THEN amount ELSE -amount END) AS balance
    FROM public.point_history
    GROUP BY user_id_fk
) sub
WHERE u.sha2_hash = sub.user_id_fk;


-- [2] watch_reservation 테이블 생성
CREATE TABLE IF NOT EXISTS public.watch_reservation (
    reservation_id  SERIAL          PRIMARY KEY,
    user_id_fk      VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    channel         INTEGER         NOT NULL,
    program_name    VARCHAR(255)    NOT NULL,
    alert_at        TIMESTAMPTZ     NOT NULL,
    notified        BOOLEAN         DEFAULT FALSE,
    created_at      TIMESTAMPTZ     DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_reservation_alert
    ON public.watch_reservation (alert_at)
    WHERE notified = FALSE;

CREATE INDEX IF NOT EXISTS idx_reservation_user
    ON public.watch_reservation (user_id_fk, alert_at ASC)
    WHERE notified = FALSE;

COMMENT ON TABLE public.watch_reservation IS
    '시청예약. 채널+시각 지정. background task(30초)가 도래 시 WebSocket 알림.';


-- [3] point_balance 자동 갱신 트리거
CREATE OR REPLACE FUNCTION fn_update_point_balance()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE public."user"
    SET point_balance = point_balance +
        CASE WHEN NEW.type = 'earn' THEN NEW.amount ELSE -NEW.amount END
    WHERE sha2_hash = NEW.user_id_fk;

    PERFORM pg_notify('user_activity',
        json_build_object('user_id', NEW.user_id_fk, 'event', 'point_change')::text);

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_point_balance ON public.point_history;
CREATE TRIGGER trg_point_balance
    AFTER INSERT ON public.point_history
    FOR EACH ROW EXECUTE FUNCTION fn_update_point_balance();


-- [4] 마이페이지 실시간 갱신 NOTIFY 트리거
CREATE OR REPLACE FUNCTION fn_notify_user_activity()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('user_activity',
        json_build_object(
            'user_id', COALESCE(NEW.user_id_fk, OLD.user_id_fk),
            'event', TG_TABLE_NAME || '_' || LOWER(TG_OP)
        )::text);
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_wishlist_notify ON public.wishlist;
CREATE TRIGGER trg_wishlist_notify
    AFTER INSERT OR DELETE ON public.wishlist
    FOR EACH ROW EXECUTE FUNCTION fn_notify_user_activity();

DROP TRIGGER IF EXISTS trg_purchase_notify ON public.purchase_history;
CREATE TRIGGER trg_purchase_notify
    AFTER INSERT ON public.purchase_history
    FOR EACH ROW EXECUTE FUNCTION fn_notify_user_activity();


-- =============================================================
-- DOWN (롤백 시)
-- =============================================================
-- DROP TRIGGER IF EXISTS trg_purchase_notify ON public.purchase_history;
-- DROP TRIGGER IF EXISTS trg_wishlist_notify ON public.wishlist;
-- DROP TRIGGER IF EXISTS trg_point_balance ON public.point_history;
-- DROP FUNCTION IF EXISTS fn_notify_user_activity();
-- DROP FUNCTION IF EXISTS fn_update_point_balance();
-- DROP TABLE IF EXISTS public.watch_reservation;
-- ALTER TABLE public."user" DROP COLUMN IF EXISTS point_balance;
