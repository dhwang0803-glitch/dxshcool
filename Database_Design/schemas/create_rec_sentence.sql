-- ============================================================
-- serving.rec_sentence — 개인화 추천 문구 (gen_rec_sentence 브랜치 생성)
-- ============================================================
-- 유저별 VOD 추천 이유 + 추천 문구를 저장.
-- 홈 "TOP10 추천 시리즈" 배너에서 포스터 위에 표시.
--
-- 생성: gen_rec_sentence 브랜치 (LLM 기반 문구 생성)
-- 소비: API_Server /home/sections/{user_id}
-- ============================================================

CREATE TABLE IF NOT EXISTS serving.rec_sentence (
    rec_sentence_id  SERIAL PRIMARY KEY,
    user_id_fk       VARCHAR(64) NOT NULL
                     REFERENCES public."user"(sha2_hash) ON DELETE CASCADE,
    vod_id_fk        VARCHAR(64) NOT NULL
                     REFERENCES public.vod(full_asset_id) ON DELETE CASCADE,
    rec_reason       TEXT NOT NULL,       -- 포스터 우측 상단: TOP10 선정 이유
                                          -- 예: "파스텔 톤의 부드러운 영화"
    rec_sentence     TEXT NOT NULL,       -- 포스터 하단: 추천 문구
                                          -- 예: "긴장감 넘치는 전개가 당신을 사로잡을 작품"
    generated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at       TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),

    CONSTRAINT uq_rec_sentence_user_vod UNIQUE (user_id_fk, vod_id_fk)
);

-- API 조회 패턴: user_id_fk 기준 score 상위 10건 JOIN
CREATE INDEX idx_rec_sentence_user ON serving.rec_sentence (user_id_fk);
CREATE INDEX idx_rec_sentence_expires ON serving.rec_sentence (expires_at)
    WHERE expires_at IS NOT NULL;

COMMENT ON TABLE serving.rec_sentence IS '개인화 추천 문구 — gen_rec_sentence 브랜치 생성, API_Server 소비';
