-- =============================================================
-- Migration: api_user 역할 생성 + 최소 권한 부여
-- Date: 2026-04-08
-- Purpose: API 서버 전용 DB 사용자 분리 (최소 권한 원칙)
--
-- 실행 순서:
--   1단계: 이 파일 실행 (역할 생성 + GRANT) ← 지금
--   2단계: dev 서버 .env DB_USER=api_user 전환 + 테스트
--   3단계: 운영 서버 전환
-- =============================================================

BEGIN;

-- 1. 역할 생성 (비밀번호는 실행 시 직접 지정)
-- CREATE USER api_user WITH PASSWORD '실행시_직접_입력';

-- 2. 스키마 사용 권한
GRANT USAGE ON SCHEMA public  TO api_user;
GRANT USAGE ON SCHEMA serving TO api_user;

-- =============================================================
-- 3. serving 스키마 — SELECT 전체 허용 (Gold 레이어, 읽기 전용)
-- =============================================================
GRANT SELECT ON ALL TABLES IN SCHEMA serving TO api_user;

-- 향후 serving에 새 테이블/MV 추가 시에도 자동 SELECT 부여
ALTER DEFAULT PRIVILEGES IN SCHEMA serving
    GRANT SELECT ON TABLES TO api_user;

-- =============================================================
-- 4. public 스키마 — 읽기 전용 테이블 (SELECT만)
-- =============================================================
GRANT SELECT ON public.vod                  TO api_user;
GRANT SELECT ON public."user"               TO api_user;
GRANT SELECT ON public.user_segment         TO api_user;
GRANT SELECT ON public.user_embedding       TO api_user;
GRANT SELECT ON public.vod_series_embedding TO api_user;
GRANT SELECT ON public.vod_meta_embedding   TO api_user;
GRANT SELECT ON public.seasonal_market      TO api_user;

-- =============================================================
-- 5. public 스키마 — 읽기 + 쓰기 테이블
-- =============================================================

-- episode_progress: SELECT + INSERT + UPDATE (UPSERT)
GRANT SELECT, INSERT, UPDATE
    ON public.episode_progress TO api_user;

-- purchase_history: SELECT + INSERT
GRANT SELECT, INSERT
    ON public.purchase_history TO api_user;

-- point_history: SELECT + INSERT (트리거가 user.point_balance 자동 갱신)
GRANT SELECT, INSERT
    ON public.point_history TO api_user;

-- wishlist: SELECT + INSERT + DELETE
GRANT SELECT, INSERT, DELETE
    ON public.wishlist TO api_user;

-- watch_reservation: SELECT + INSERT + UPDATE + DELETE
GRANT SELECT, INSERT, UPDATE, DELETE
    ON public.watch_reservation TO api_user;
-- SERIAL PK 시퀀스 사용 권한
GRANT USAGE, SELECT
    ON SEQUENCE public.watch_reservation_reservation_id_seq TO api_user;

-- notifications: SELECT + UPDATE + DELETE (읽음 처리, 삭제)
GRANT SELECT, UPDATE, DELETE
    ON public.notifications TO api_user;

-- =============================================================
-- 6. PG LISTEN 권한 (실시간 알림용)
-- =============================================================
-- LISTEN/NOTIFY는 별도 GRANT 불필요 (CONNECT 권한만 있으면 됨)

-- =============================================================
-- 7. search_path 기본값 설정
-- =============================================================
ALTER USER api_user SET search_path = serving, public;

COMMIT;

-- =============================================================
-- 검증 쿼리 (실행 후 확인용)
-- =============================================================
-- SELECT grantee, table_schema, table_name, privilege_type
-- FROM information_schema.table_privileges
-- WHERE grantee = 'api_user'
-- ORDER BY table_schema, table_name, privilege_type;
