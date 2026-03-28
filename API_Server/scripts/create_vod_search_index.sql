-- ============================================================
-- serving.vod_search_index — 검색용 Materialized View
-- 초성 검색 + pg_trgm 일반 검색 지원
-- ============================================================

-- 1) pg_trgm 확장 (이미 있으면 무시)
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 2) 한글 초성 변환 함수
CREATE OR REPLACE FUNCTION serving.to_chosung(input TEXT)
RETURNS TEXT
LANGUAGE plpgsql IMMUTABLE STRICT AS $$
DECLARE
    ch       INT;
    result   TEXT := '';
    i        INT;
    len      INT;
    chosung  TEXT[] := ARRAY[
        'ㄱ','ㄲ','ㄴ','ㄷ','ㄸ','ㄹ','ㅁ','ㅂ','ㅃ',
        'ㅅ','ㅆ','ㅇ','ㅈ','ㅉ','ㅊ','ㅋ','ㅌ','ㅍ','ㅎ'
    ];
BEGIN
    len := char_length(input);
    FOR i IN 1..len LOOP
        ch := ascii(substr(input, i, 1));
        IF ch >= 44032 AND ch <= 55203 THEN
            -- 한글 완성형 → 초성 추출
            result := result || chosung[((ch - 44032) / 588) + 1];
        ELSE
            -- 숫자, 영문, 공백 등은 그대로
            result := result || substr(input, i, 1);
        END IF;
    END LOOP;
    RETURN result;
END;
$$;

-- 3) Materialized View 생성
DROP MATERIALIZED VIEW IF EXISTS serving.vod_search_index;

CREATE MATERIALIZED VIEW serving.vod_search_index AS
SELECT
    COALESCE(series_nm, asset_nm)  AS series_nm,
    asset_nm,
    genre,
    ct_cl,
    poster_url,
    director,
    cast_lead,
    serving.to_chosung(COALESCE(series_nm, asset_nm)) AS series_nm_chosung,
    -- 검색 대상 통합 텍스트 (trgm 인덱스용)
    COALESCE(series_nm, asset_nm) || ' ' ||
        COALESCE(cast_lead, '') || ' ' ||
        COALESCE(director, '') || ' ' ||
        COALESCE(genre, '')    AS search_text
FROM (
    SELECT DISTINCT ON (COALESCE(series_nm, asset_nm))
        series_nm, asset_nm, genre, ct_cl, poster_url, director, cast_lead
    FROM public.vod
    ORDER BY COALESCE(series_nm, asset_nm), asset_nm
) sub;

-- 4) 인덱스
-- 일반 검색: pg_trgm GIN
CREATE INDEX idx_vod_search_trgm
ON serving.vod_search_index
USING gin (search_text gin_trgm_ops);

-- 초성 검색: btree (LIKE prefix 지원)
CREATE INDEX idx_vod_search_chosung
ON serving.vod_search_index
USING btree (series_nm_chosung text_pattern_ops);

-- 확인
SELECT COUNT(*) AS total_rows FROM serving.vod_search_index;
SELECT series_nm, series_nm_chosung
FROM serving.vod_search_index
WHERE series_nm LIKE '응답하라%'
LIMIT 3;
