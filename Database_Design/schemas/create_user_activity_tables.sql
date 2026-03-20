-- =============================================================
-- 유저 활동 테이블 DDL (public 스키마)
-- 파일: Database_Design/schemas/create_user_activity_tables.sql
-- 목적: Frontend 연동에 필요한 유저 활동 데이터 저장
-- 작성일: 2026-03-20
-- 배경:
--   Frontend UI(마이페이지, 시리즈 상세, 구매) 연동을 위해
--   기존 watch_history(ML 전용)와 별도로 유저 활동 테이블 4개 신설.
--   watch_history는 추천 엔진 입력 전용, API 응답에는 이 테이블들을 사용.
-- 소비 브랜치: API_Server(읽기/쓰기)
-- =============================================================
-- 실행 전제: create_tables.sql 이 먼저 실행되어 있어야 함
-- 실행 방법: psql -U <user> -d <dbname> -f create_user_activity_tables.sql
-- =============================================================


-- =============================================================
-- [1] wishlist — 찜 목록
--     시리즈 단위 찜. series_nm 기준 그룹핑.
--     series_nm은 vod 테이블에서 UNIQUE가 아닌 그룹핑 키이므로 FK 없음.
-- =============================================================

CREATE TABLE public.wishlist (
    user_id_fk      VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    series_nm       VARCHAR(255)    NOT NULL,
    created_at      TIMESTAMPTZ     DEFAULT NOW(),

    PRIMARY KEY (user_id_fk, series_nm)
);

-- 유저별 찜 목록 최신순 조회: WHERE user_id_fk = $1 ORDER BY created_at DESC
CREATE INDEX idx_wishlist_user_created
    ON public.wishlist (user_id_fk, created_at DESC);

COMMENT ON TABLE public.wishlist IS
    '유저 찜 목록. 시리즈 단위. API_Server에서 읽기/쓰기.';
COMMENT ON COLUMN public.wishlist.user_id_fk IS
    'FK → "user".sha2_hash (ON DELETE CASCADE)';
COMMENT ON COLUMN public.wishlist.series_nm IS
    '찜한 시리즈명 (vod.series_nm 그룹핑 키). 시즌 포함 시 "라바 시즌1" 형태.';
COMMENT ON COLUMN public.wishlist.created_at IS
    '찜 등록 시각';


-- =============================================================
-- [2] episode_progress — 에피소드별 시청 진행률
--     에피소드(vod) 단위 진행률 저장. 이어보기/시청 현황 UI에 사용.
--     watch_history(ML 전용)와 역할 분리:
--       watch_history → 추천 엔진 입력 (REAL 0.0~1.0)
--       episode_progress → API 응답용 (SMALLINT 0~100)
-- =============================================================

CREATE TABLE public.episode_progress (
    user_id_fk      VARCHAR(64)     NOT NULL REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
    vod_id_fk       VARCHAR(64)     NOT NULL REFERENCES vod(full_asset_id) ON DELETE CASCADE,
    series_nm       VARCHAR(255)    NOT NULL,
    completion_rate SMALLINT        NOT NULL DEFAULT 0,
    watched_at      TIMESTAMPTZ     DEFAULT NOW(),

    PRIMARY KEY (user_id_fk, vod_id_fk),

    CONSTRAINT chk_ep_completion_rate CHECK (completion_rate BETWEEN 0 AND 100)
);

-- 시리즈 상세 페이지: 특정 유저의 특정 시리즈 에피소드 진행 현황
-- WHERE user_id_fk = $1 AND series_nm = $2 ORDER BY watched_at DESC
CREATE INDEX idx_ep_progress_user_series
    ON public.episode_progress (user_id_fk, series_nm, watched_at DESC);

-- 시청 중인 콘텐츠 조회 (홈): WHERE user_id_fk = $1 ORDER BY watched_at DESC LIMIT N
-- PK 인덱스(user_id_fk, vod_id_fk)와 별도로 watched_at 정렬 필요
CREATE INDEX idx_ep_progress_user_watched
    ON public.episode_progress (user_id_fk, watched_at DESC)
    INCLUDE (vod_id_fk, series_nm, completion_rate);

-- updated_at 역할을 watched_at이 수행하므로 별도 트리거 불필요

COMMENT ON TABLE public.episode_progress IS
    '에피소드별 시청 진행률. API 응답 전용 (watch_history는 ML 전용). 정수 0~100%.';
COMMENT ON COLUMN public.episode_progress.user_id_fk IS
    'FK → "user".sha2_hash (ON DELETE CASCADE)';
COMMENT ON COLUMN public.episode_progress.vod_id_fk IS
    'FK → vod.full_asset_id (ON DELETE CASCADE). 에피소드 단위.';
COMMENT ON COLUMN public.episode_progress.series_nm IS
    '비정규화된 시리즈명 (조인 없이 시리즈 그룹핑 가능). vod.series_nm과 동일값.';
COMMENT ON COLUMN public.episode_progress.completion_rate IS
    '시청 진행률 정수 (0~100). 연산식: ROUND(use_tms / disp_rtm_sec * 100).';
COMMENT ON COLUMN public.episode_progress.watched_at IS
    '최종 시청 시각. ON CONFLICT UPDATE 시 갱신.';


-- =============================================================
-- [3] purchase_history — 구매 내역
--     시리즈 단위 구매/대여 기록. 포인트 결제.
--     대여(rental): expires_at = purchased_at + 48h
--     영구(permanent): expires_at = NULL
-- =============================================================

CREATE TABLE public.purchase_history (
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

-- 유저별 구매 내역 조회: WHERE user_id_fk = $1 ORDER BY purchased_at DESC
CREATE INDEX idx_purchase_user_date
    ON public.purchase_history (user_id_fk, purchased_at DESC);

-- 특정 시리즈 구매 여부 확인: WHERE user_id_fk = $1 AND series_nm = $2
-- 대여 만료 체크: AND (expires_at IS NULL OR expires_at > NOW())
CREATE INDEX idx_purchase_user_series
    ON public.purchase_history (user_id_fk, series_nm)
    INCLUDE (option_type, expires_at);

COMMENT ON TABLE public.purchase_history IS
    '포인트 기반 VOD 구매/대여 내역. 시리즈 단위.';
COMMENT ON COLUMN public.purchase_history.purchase_id IS
    '자동 생성 구매 ID';
COMMENT ON COLUMN public.purchase_history.user_id_fk IS
    'FK → "user".sha2_hash (ON DELETE CASCADE)';
COMMENT ON COLUMN public.purchase_history.series_nm IS
    '구매한 시리즈명. 시즌 포함 시 "라바 시즌1" 형태.';
COMMENT ON COLUMN public.purchase_history.option_type IS
    'rental: 48시간 대여 | permanent: 영구 소장';
COMMENT ON COLUMN public.purchase_history.points_used IS
    '사용 포인트 (양수). 환율: 원 ÷ 10 = P (협의 필요).';
COMMENT ON COLUMN public.purchase_history.purchased_at IS
    '구매 시각';
COMMENT ON COLUMN public.purchase_history.expires_at IS
    '대여 만료 시각. rental: purchased_at + 48h. permanent: NULL.';


-- =============================================================
-- [4] point_history — 포인트 적립/사용 내역
--     point_balance는 이 테이블에서 실시간 집계:
--     SUM(CASE WHEN type='earn' THEN amount ELSE -amount END)
--     Redis 캐시 레이어 도입 검토 중 (추후 논의).
-- =============================================================

CREATE TABLE public.point_history (
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

-- 유저별 포인트 내역 최신순: WHERE user_id_fk = $1 ORDER BY created_at DESC
CREATE INDEX idx_point_history_user_date
    ON public.point_history (user_id_fk, created_at DESC);

-- 포인트 잔액 집계: SELECT SUM(CASE WHEN type='earn' THEN amount ELSE -amount END)
--                   FROM point_history WHERE user_id_fk = $1
-- 위 쿼리에 user_id_fk 인덱스 활용. 대량 데이터 시 Redis 캐시 도입 예정.

COMMENT ON TABLE public.point_history IS
    '포인트 적립/사용 내역. point_balance = SUM(earn) - SUM(use). Redis 캐시 검토 중.';
COMMENT ON COLUMN public.point_history.point_history_id IS
    '자동 생성 내역 ID';
COMMENT ON COLUMN public.point_history.user_id_fk IS
    'FK → "user".sha2_hash (ON DELETE CASCADE)';
COMMENT ON COLUMN public.point_history.type IS
    'earn: 적립 | use: 사용';
COMMENT ON COLUMN public.point_history.amount IS
    '포인트 금액 (양수). type에 따라 적립/차감 해석.';
COMMENT ON COLUMN public.point_history.description IS
    '내역 설명 (예: "라바 시즌1 대여", "신규 가입 보너스")';
COMMENT ON COLUMN public.point_history.related_purchase_id IS
    'FK → purchase_history.purchase_id. 구매 차감인 경우 연결. 적립은 NULL.';
COMMENT ON COLUMN public.point_history.created_at IS
    '내역 생성 시각';
