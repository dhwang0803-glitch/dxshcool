-- =============================================================
-- Phase 3B OPT-1: 커버링 인덱스 + 부분 인덱스
-- 파일: Database_Design/schema/create_opt_indexes.sql
-- 작성일: 2026-03-07
-- 참조: PLAN_03B_PERFORMANCE_OPT.md
-- =============================================================
-- 주의: CONCURRENTLY는 트랜잭션 밖에서 실행해야 함 (autocommit)
--       각 인덱스 생성 중 watch_history 쓰기 정상 진행 (읽기 락 없음)
--       4M rows 기준 인덱스당 30~60분 소요 예상
-- =============================================================

-- [OPT-1-A] 커버링 인덱스: P01 vod Seq Scan → Nested Loop 전환 유도
-- (user_id_fk, strt_dt DESC): 사용자별 최신순 정렬 Sort 단계 제거
-- INCLUDE(vod_id_fk, completion_rate, satisfaction): heap fetch 없이 커버
CREATE INDEX CONCURRENTLY idx_wh_user_covering
    ON watch_history (user_id_fk, strt_dt DESC)
    INCLUDE (vod_id_fk, completion_rate, satisfaction);

-- [OPT-1-B] 부분 인덱스: P04 satisfaction > 0 필터 최적화
-- satisfaction > 0인 2.98M rows만 인덱스에 포함
-- ORDER BY satisfaction DESC 쿼리에서 인덱스 순서 활용
CREATE INDEX CONCURRENTLY idx_wh_satisfaction_nonzero
    ON watch_history (satisfaction DESC)
    WHERE satisfaction > 0;
