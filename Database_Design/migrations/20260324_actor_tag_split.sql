-- =============================================================
-- actor 태그 → actor_lead / actor_guest 분리
-- 배경: cast_lead(주연)와 cast_guest(게스트)를 구분하여
--       TV 연예/오락 게스트 출연은 에피소드 단위,
--       그 외 주연은 시리즈 단위로 추천하기 위함
-- =============================================================

-- 1) CHECK 제약 교체
ALTER TABLE public.vod_tag DROP CONSTRAINT chk_vt_category;
ALTER TABLE public.vod_tag ADD CONSTRAINT chk_vt_category CHECK (
    tag_category IN ('director', 'actor_lead', 'actor_guest', 'genre', 'genre_detail', 'rating')
);

-- 2) 기존 'actor' 태그를 'actor_lead'로 일괄 변환
--    (기존 데이터는 cast_lead+cast_guest 혼합이지만,
--     Phase 1 재실행 시 정확히 분리되므로 임시 변환)
UPDATE public.vod_tag
SET tag_category = 'actor_lead'
WHERE tag_category = 'actor';

-- 3) COMMENT 갱신
COMMENT ON COLUMN public.vod_tag.tag_category IS
    '태그 카테고리: director, actor_lead, actor_guest, genre, genre_detail, rating';

-- 확인
SELECT tag_category, COUNT(*) FROM public.vod_tag GROUP BY tag_category ORDER BY tag_category;
