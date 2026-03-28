-- =============================================================
-- 마이그레이션: notifications 테이블 + GNB 통합 검색 인덱스
-- 날짜: 2026-03-21
-- 배경:
--   프론트엔드 추가 요청 (BACKEND_TODO.md):
--   1) 알림 시스템 — GNB 알림 벨에 신규 에피소드/시청예약/시스템 알림 표시
--   2) GNB 통합 검색 — asset_nm/cast_lead/director/genre 4컬럼 ILIKE 검색
-- 영향 브랜치: API_Server (읽기/쓰기)
-- =============================================================


-- [1] notifications 테이블
CREATE TABLE IF NOT EXISTS public.notifications (
    notification_id  SERIAL          PRIMARY KEY,
    user_id_fk       VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    type             VARCHAR(32)     NOT NULL,
    title            VARCHAR(255)    NOT NULL,
    message          VARCHAR(512)    NOT NULL,
    image_url        TEXT,
    read             BOOLEAN         NOT NULL DEFAULT FALSE,
    created_at       TIMESTAMPTZ     DEFAULT NOW(),

    CONSTRAINT chk_notification_type CHECK (type IN ('new_episode', 'reservation', 'system'))
);

-- 유저별 알림 목록 (최신순): WHERE user_id_fk = $1 ORDER BY created_at DESC
CREATE INDEX IF NOT EXISTS idx_notifications_user_created
    ON public.notifications (user_id_fk, created_at DESC);

-- 미읽음 알림 카운트: WHERE user_id_fk = $1 AND read = FALSE
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread
    ON public.notifications (user_id_fk)
    WHERE read = FALSE;

COMMENT ON TABLE public.notifications IS
    '유저 알림. GNB 벨 표시. type: new_episode(신규 에피소드) / reservation(시청예약) / system(시스템).';
COMMENT ON COLUMN public.notifications.notification_id IS '자동 생성 알림 ID';
COMMENT ON COLUMN public.notifications.user_id_fk IS 'FK -> "user".sha2_hash (ON DELETE CASCADE)';
COMMENT ON COLUMN public.notifications.type IS 'new_episode: 찜 시리즈 신규 에피소드 | reservation: 시청예약 도래 | system: 시스템 공지';
COMMENT ON COLUMN public.notifications.title IS '알림 제목 (시리즈명 또는 프로그램명)';
COMMENT ON COLUMN public.notifications.message IS '알림 본문';
COMMENT ON COLUMN public.notifications.image_url IS '알림 썸네일 (포스터 등). NULL 허용.';
COMMENT ON COLUMN public.notifications.read IS '읽음 여부. PATCH로 TRUE 전환.';
COMMENT ON COLUMN public.notifications.created_at IS '알림 생성 시각';


-- [2] 신규 에피소드 알림 트리거
--     vod INSERT 시 동일 series_nm을 찜한 유저에게 new_episode 알림 자동 생성.
--     series_nm이 NULL이면 단편이므로 알림 미발송.
CREATE OR REPLACE FUNCTION fn_notify_new_episode()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.series_nm IS NOT NULL THEN
        INSERT INTO public.notifications (user_id_fk, type, title, message, image_url)
        SELECT w.user_id_fk,
               'new_episode',
               NEW.series_nm,
               NEW.asset_nm || ' 새로운 에피소드가 등록되었습니다',
               NEW.poster_url
        FROM public.wishlist w
        WHERE w.series_nm = NEW.series_nm;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_new_episode_notify ON public.vod;
CREATE TRIGGER trg_new_episode_notify
    AFTER INSERT ON public.vod
    FOR EACH ROW EXECUTE FUNCTION fn_notify_new_episode();


-- [3] GNB 통합 검색 — pg_trgm GIN 인덱스
--     asset_nm, cast_lead, director, genre 4컬럼 ILIKE 검색 지원.
--     concat으로 결합 후 단일 GIN 인덱스로 커버.
CREATE INDEX IF NOT EXISTS idx_vod_search_trgm
    ON public.vod
    USING GIN (
        (COALESCE(asset_nm, '') || ' ' ||
         COALESCE(cast_lead, '') || ' ' ||
         COALESCE(director, '') || ' ' ||
         COALESCE(genre, ''))
        gin_trgm_ops
    );


-- =============================================================
-- DOWN (롤백 시)
-- =============================================================
-- DROP INDEX IF EXISTS idx_vod_search_trgm;
-- DROP TRIGGER IF EXISTS trg_new_episode_notify ON public.vod;
-- DROP FUNCTION IF EXISTS fn_notify_new_episode();
-- DROP TABLE IF EXISTS public.notifications;
