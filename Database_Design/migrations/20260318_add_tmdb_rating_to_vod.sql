-- 인기도 스코어 산출용 TMDB 평점 컬럼 3종 추가
-- 설계: docs/POPULARITY_SCORE_DESIGN.md §5-1

BEGIN;

ALTER TABLE vod
    ADD COLUMN IF NOT EXISTS tmdb_vote_average REAL,
    ADD COLUMN IF NOT EXISTS tmdb_vote_count   INTEGER,
    ADD COLUMN IF NOT EXISTS tmdb_popularity   REAL;

COMMENT ON COLUMN vod.tmdb_vote_average IS 'TMDB 평점 (0.0~10.0). RAG 파이프라인이 수집.';
COMMENT ON COLUMN vod.tmdb_vote_count   IS 'TMDB 평가 참여자 수. vote_score 산출에 사용.';
COMMENT ON COLUMN vod.tmdb_popularity   IS 'TMDB 인기도 점수. 참고용 저장, 인기도 공식에는 미사용 (왜곡 우려).';

COMMIT;
