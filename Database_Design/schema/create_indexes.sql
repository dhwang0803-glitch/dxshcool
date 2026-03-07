-- =============================================================
-- Phase 1: 인덱스 생성 스크립트
-- 파일: Database_Design/schema/create_indexes.sql
-- 목적: 조회 성능 최적화를 위한 인덱스 생성
-- 작성일: 2026-03-07
-- 참조: PLAN_01_SCHEMA_DDL.md (섹션 5. 인덱스 설계)
-- =============================================================
-- 실행 전제: create_tables.sql이 먼저 실행되어 있어야 함
-- 실행 방법: psql -U <user> -d <dbname> -f create_indexes.sql
-- =============================================================


-- =============================================================
-- [1] watch_history 인덱스 (HIGH 우선순위)
--     3,992,530건 대용량 테이블 - 조회 패턴 최우선 최적화
-- =============================================================

-- 사용자별 시청이력 조회 (WHERE user_id_fk = ?)
-- 목표 응답시간: < 100ms
CREATE INDEX idx_wh_user_id
    ON watch_history (user_id_fk);

-- VOD별 시청 통계 조회 (WHERE vod_id_fk = ?)
-- 목표 응답시간: < 100ms
CREATE INDEX idx_wh_vod_id
    ON watch_history (vod_id_fk);

-- 날짜 범위 조회 (WHERE strt_dt BETWEEN ? AND ?)
-- 목표 응답시간: < 500ms
CREATE INDEX idx_wh_strt_dt
    ON watch_history (strt_dt);

-- 만족도 순위 조회 (ORDER BY satisfaction DESC)
-- 목표 응답시간: < 500ms
CREATE INDEX idx_wh_satisfaction
    ON watch_history (satisfaction);

-- 사용자별 시간순 조회 복합 인덱스 (WHERE user_id_fk = ? ORDER BY strt_dt)
-- idx_wh_user_id 단독 인덱스보다 시간 정렬 쿼리에서 더 효율적
CREATE INDEX idx_wh_user_strt
    ON watch_history (user_id_fk, strt_dt);


-- =============================================================
-- [2] vod 인덱스 (MEDIUM 우선순위)
--     166,159건 - 콘텐츠 필터링 및 텍스트 검색 최적화
-- =============================================================

-- 콘텐츠 대분류 필터링 (WHERE ct_cl = '영화')
CREATE INDEX idx_vod_ct_cl
    ON vod (ct_cl);

-- 장르 필터링 (WHERE genre = '액션')
CREATE INDEX idx_vod_genre
    ON vod (genre);

-- 제공사 필터링 (WHERE provider = ?)
CREATE INDEX idx_vod_provider
    ON vod (provider);

-- 줄거리 전문 검색 GIN 인덱스 (MySQL FULLTEXT INDEX 대체)
-- 'korean' 텍스트 설정이 없는 환경에서는 아래 주석을 해제하고 'simple' 사용:
-- CREATE INDEX idx_vod_smry_gin ON vod USING GIN (to_tsvector('simple', coalesce(smry,'')));
CREATE INDEX idx_vod_smry_gin
    ON vod USING GIN (to_tsvector('simple', coalesce(smry, '')));


-- =============================================================
-- [3] "user" 인덱스 (LOW 우선순위)
--     242,702건 - 사용자 세그먼트 필터링
-- =============================================================

-- 연령대별 필터링 (WHERE age_grp10 = '30대')
CREATE INDEX idx_user_age_grp
    ON "user" (age_grp10);

-- Netflix 사용 여부 필터링 (WHERE nfx_use_yn = TRUE)
CREATE INDEX idx_user_nfx
    ON "user" (nfx_use_yn);
