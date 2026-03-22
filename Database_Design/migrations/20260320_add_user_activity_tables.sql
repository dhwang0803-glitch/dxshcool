-- =============================================================
-- 마이그레이션: 유저 활동 테이블 4개 추가
-- 파일: Database_Design/migrations/20260320_add_user_activity_tables.sql
-- 작성일: 2026-03-20
-- 배경:
--   Frontend UI 연동을 위해 유저 활동 테이블 4개 신설.
--   기존 watch_history는 ML 파이프라인 전용으로 한정.
--   API 응답은 이 테이블들을 사용한다.
-- 영향 브랜치: API_Server(읽기/쓰기)
-- =============================================================

-- UP: 테이블 4개 생성 + 인덱스

-- [1] wishlist
CREATE TABLE IF NOT EXISTS public.wishlist (
    user_id_fk      VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    series_nm       VARCHAR(255)    NOT NULL,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (user_id_fk, series_nm)
);
CREATE INDEX IF NOT EXISTS idx_wishlist_user_created
    ON public.wishlist (user_id_fk, created_at DESC);

-- [2] episode_progress
CREATE TABLE IF NOT EXISTS public.episode_progress (
    user_id_fk      VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    vod_id_fk       VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    series_nm       VARCHAR(255)    NOT NULL,
    completion_rate SMALLINT        NOT NULL DEFAULT 0,
    watched_at      TIMESTAMPTZ     DEFAULT NOW(),
    PRIMARY KEY (user_id_fk, vod_id_fk),
    CONSTRAINT chk_ep_completion_rate CHECK (completion_rate BETWEEN 0 AND 100)
);
CREATE INDEX IF NOT EXISTS idx_ep_progress_user_series
    ON public.episode_progress (user_id_fk, series_nm, watched_at DESC);
CREATE INDEX IF NOT EXISTS idx_ep_progress_user_watched
    ON public.episode_progress (user_id_fk, watched_at DESC)
    INCLUDE (vod_id_fk, series_nm, completion_rate);

-- [3] purchase_history
CREATE TABLE IF NOT EXISTS public.purchase_history (
    purchase_id     BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk      VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    series_nm       VARCHAR(255)    NOT NULL,
    option_type     VARCHAR(16)     NOT NULL,
    points_used     INTEGER         NOT NULL,
    purchased_at    TIMESTAMPTZ     DEFAULT NOW(),
    expires_at      TIMESTAMPTZ,
    CONSTRAINT chk_purchase_option  CHECK (option_type IN ('rental', 'permanent')),
    CONSTRAINT chk_purchase_points  CHECK (points_used >= 0)
);
CREATE INDEX IF NOT EXISTS idx_purchase_user_date
    ON public.purchase_history (user_id_fk, purchased_at DESC);
CREATE INDEX IF NOT EXISTS idx_purchase_user_series
    ON public.purchase_history (user_id_fk, series_nm)
    INCLUDE (option_type, expires_at);

-- [4] point_history
CREATE TABLE IF NOT EXISTS public.point_history (
    point_history_id BIGINT         GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id_fk       VARCHAR(64)    NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    type             VARCHAR(8)     NOT NULL,
    amount           INTEGER        NOT NULL,
    description      VARCHAR(256)   NOT NULL,
    related_purchase_id BIGINT      REFERENCES public.purchase_history(purchase_id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ    DEFAULT NOW(),
    CONSTRAINT chk_point_type   CHECK (type IN ('use', 'earn')),
    CONSTRAINT chk_point_amount CHECK (amount > 0)
);
CREATE INDEX IF NOT EXISTS idx_point_history_user_date
    ON public.point_history (user_id_fk, created_at DESC);


-- DOWN: 롤백 (역순 DROP — FK 의존성 고려)
-- DROP TABLE IF EXISTS public.point_history;
-- DROP TABLE IF EXISTS public.purchase_history;
-- DROP TABLE IF EXISTS public.episode_progress;
-- DROP TABLE IF EXISTS public.wishlist;
