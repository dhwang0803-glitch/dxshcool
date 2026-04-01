-- =============================================================
-- 마이그레이션: vod_series_embedding 시리즈 대표 임베딩 테이블
-- 날짜: 2026-03-26
-- 목적: vod_meta_embedding 에피소드 중복 해소 (166K → ~11.5K 시리즈)
--
-- 배경:
--   vod_meta_embedding은 에피소드 단위(166,159건)로 적재되어 있다.
--   같은 시리즈의 에피소드들은 메타데이터가 동일하므로 코사인 유사도 0.999.
--   LIMIT 60 벡터 검색 시 1~3개 시리즈 에피소드만 반환되는 문제 발생.
--
-- 해법:
--   시리즈당 대표 1건(poster_url 있는 첫 에피소드)의 임베딩을 저장.
--   Vector_Search가 이 테이블을 조회하면 시리즈 다양성이 보장된다.
--
-- 영향 브랜치: VOD_Embedding(적재), Vector_Search(읽기)
-- =============================================================

-- [1] 테이블 생성
CREATE TABLE IF NOT EXISTS public.vod_series_embedding (
    series_emb_id       BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- 시리즈 식별 (vod.series_nm 기준 그룹핑)
    series_nm           VARCHAR(255)    NOT NULL UNIQUE,

    -- 대표 VOD (poster_url 있는 첫 에피소드)
    representative_vod_id VARCHAR(64)   NOT NULL,

    -- 메타 임베딩 벡터 (384차원, vod_meta_embedding과 동일 모델)
    embedding           VECTOR(384)     NOT NULL,

    -- 서빙 편의 컬럼 (JOIN 없이 API 응답 가능)
    ct_cl               VARCHAR(64),
    poster_url          TEXT,

    -- 시리즈 통계
    episode_count       INTEGER         NOT NULL DEFAULT 1,

    -- 모델 정보
    model_name          VARCHAR(100)    NOT NULL
                            DEFAULT 'paraphrase-multilingual-MiniLM-L12-v2',

    -- 시간
    created_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- 제약
    CONSTRAINT fk_series_emb_vod
        FOREIGN KEY (representative_vod_id) REFERENCES vod(full_asset_id) ON DELETE CASCADE
);

-- [2] IVFFlat 인덱스 (코사인 유사도)
-- lists = 100 : sqrt(~11,520) ≈ 107
CREATE INDEX idx_vod_series_emb_ivfflat
    ON public.vod_series_embedding
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- ct_cl 필터 인덱스
CREATE INDEX idx_vod_series_emb_ct_cl
    ON public.vod_series_embedding (ct_cl);

CREATE INDEX idx_vod_series_emb_updated
    ON public.vod_series_embedding (updated_at DESC);

-- [3] updated_at 자동 갱신 트리거
CREATE TRIGGER trg_vod_series_emb_updated_at
    BEFORE UPDATE ON public.vod_series_embedding
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- [4] 코멘트
COMMENT ON TABLE public.vod_series_embedding IS
    '시리즈 대표 메타 임베딩. vod_meta_embedding(에피소드 166K)에서 시리즈당 1건 추출. '
    'Vector_Search 벡터 검색 시 시리즈 다양성 보장 목적.';
COMMENT ON COLUMN public.vod_series_embedding.series_nm IS
    'vod.series_nm 기준 그룹핑. 시리즈가 없는 단편은 asset_nm 사용.';
COMMENT ON COLUMN public.vod_series_embedding.representative_vod_id IS
    '시리즈 대표 에피소드 ID. poster_url 있는 첫 에피소드 우선 선정.';
COMMENT ON COLUMN public.vod_series_embedding.episode_count IS
    '해당 시리즈의 vod_meta_embedding 에피소드 수.';


-- =============================================================
-- [5] 초기 데이터 적재 (vod_meta_embedding → vod_series_embedding)
--
-- 선정 기준:
--   시리즈별 poster_url IS NOT NULL인 에피소드 중 첫 번째(full_asset_id 순)
--   poster_url 없으면 아무 에피소드 1건
-- =============================================================

INSERT INTO public.vod_series_embedding
    (series_nm, representative_vod_id, embedding, ct_cl, poster_url, episode_count)
SELECT
    series_nm,
    representative_vod_id,
    embedding,
    ct_cl,
    poster_url,
    episode_count
FROM (
    SELECT
        COALESCE(v.series_nm, v.asset_nm)           AS series_nm,
        v.full_asset_id                              AS representative_vod_id,
        vme.embedding,
        v.ct_cl,
        v.poster_url,
        COUNT(*) OVER (PARTITION BY COALESCE(v.series_nm, v.asset_nm)) AS episode_count,
        ROW_NUMBER() OVER (
            PARTITION BY COALESCE(v.series_nm, v.asset_nm)
            ORDER BY
                (v.poster_url IS NOT NULL) DESC,     -- poster 있는 에피소드 우선
                v.full_asset_id ASC                   -- 결정적 순서
        ) AS rn
    FROM public.vod_meta_embedding vme
    JOIN public.vod v ON v.full_asset_id = vme.vod_id_fk
) ranked
WHERE rn = 1
ON CONFLICT (series_nm) DO UPDATE SET
    representative_vod_id = EXCLUDED.representative_vod_id,
    embedding             = EXCLUDED.embedding,
    ct_cl                 = EXCLUDED.ct_cl,
    poster_url            = EXCLUDED.poster_url,
    episode_count         = EXCLUDED.episode_count,
    updated_at            = NOW();
