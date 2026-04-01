-- ============================================================
-- public.user_segment — K-Means 유저 세그먼트 (gen_rec_sentence 브랜치 생성)
-- ============================================================
-- K-Means(k=5) 클러스터링 결과. 유저 시청 패턴을 5개 세그먼트로 분류.
-- rec_sentence가 세그먼트별 맞춤 문구를 생성할 때 사용.
--
-- 생성: gen_rec_sentence 브랜치
-- 소비: API_Server rec_sentence_service.py (세그먼트 결정)
-- ============================================================

CREATE TABLE IF NOT EXISTS public.user_segment (
    user_id_fk   VARCHAR(64) NOT NULL PRIMARY KEY,
    segment_id   SMALLINT    NOT NULL,
    assigned_at  TIMESTAMPTZ DEFAULT NOW()
);

COMMENT ON TABLE public.user_segment IS 'K-Means(k=5) 유저 세그먼트 — gen_rec_sentence 생성, API_Server 소비';

-- ============================================================
-- serving.rec_sentence — 세그먼트별 VOD 추천 문구 (gen_rec_sentence 브랜치 생성)
-- ============================================================
-- VOD × 세그먼트(0~4)별 맞춤 추천 문구를 저장.
-- 홈 "TOP10 추천 시리즈" 배너에서 포스터 위에 표시.
--
-- 설계 변경 이력:
--   v1(DDL 초안): user_id_fk 기반 유저별 문구 → 유저 수 × VOD 수 폭증 문제
--   v2(현행):     segment_id 기반 세그먼트별 문구 → 5 세그먼트 × VOD 수로 축소
--
-- 생성: gen_rec_sentence 브랜치 (LLM gemma3:27b-it-qat 기반 문구 생성)
-- 소비: API_Server /home/sections/{user_id} TOP10 배너
-- ============================================================

CREATE TABLE IF NOT EXISTS serving.rec_sentence (
    vod_id_fk    VARCHAR(64) NOT NULL,
    segment_id   SMALLINT    NOT NULL,
    rec_sentence TEXT        NOT NULL,
    model_name   VARCHAR(100),            -- 생성 모델 (예: 'gemma3:27b-it-qat')
    generated_at TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT rec_sentence_pkey PRIMARY KEY (vod_id_fk, segment_id)
);

-- API 조회 패턴: vod_id_fk IN (...) AND segment_id = ? → PK 커버링
COMMENT ON TABLE serving.rec_sentence IS '세그먼트별 VOD 추천 문구 — gen_rec_sentence 생성, API_Server 소비';
