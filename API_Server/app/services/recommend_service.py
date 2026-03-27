"""개인화 추천 서비스 — hybrid_recommendation + tag_recommendation 기반."""

from app.services.db import get_pool

# pattern_reason 생성용 템플릿 (추천페이지: actor/director 관점만)
_REASON_TEMPLATES = {
    "genre_detail": "{value} 장르를 즐겨 보셨어요",
    "director": "{value} 감독 작품을 즐겨 보셨어요",
    "actor_lead": "{value} 배우 출연작을 자주 보셨어요",
    "actor_guest": "{value} 배우가 출연한 프로그램을 모아봤어요",
    "cold_genre_detail": "{user}님이 좋아할만한 {value} 시리즈",
}


def _make_reason(tag_category: str, tag_value: str, user_label: str = "") -> str:
    tpl = _REASON_TEMPLATES.get(tag_category, "{value} 관련 콘텐츠를 즐겨 보셨어요")
    return tpl.format(value=tag_value, user=user_label)


async def _is_test_user(pool, user_id: str) -> bool:
    """DB에서 is_test 플래그 조회."""
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT is_test FROM public."user" WHERE sha2_hash = $1',
                user_id,
            )
        return bool(row and row["is_test"])
    except Exception:
        return False


async def get_recommendations(user_id: str) -> dict:
    pool = await get_pool()

    # 테스터 여부 확인 → 격리 테이블 분기
    is_test = await _is_test_user(pool, user_id)
    hybrid_table = "serving.hybrid_recommendation_test" if is_test else "serving.hybrid_recommendation"
    tag_table = "serving.tag_recommendation_test" if is_test else "serving.tag_recommendation"

    # 1) top_vods: hybrid score 내림차순 top 5 (backdrop_url 없으면 다음 순위로)
    #    부족분은 cold_genre_detail (age_grp10 기반 연령대 맞춤 VOD)로 보충
    top_vods = []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT r.vod_id_fk, v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url
                FROM {hybrid_table} r
                JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                WHERE r.user_id_fk = $1
                  AND v.backdrop_url IS NOT NULL
                  AND (r.expires_at IS NULL OR r.expires_at > NOW())
                ORDER BY r.score DESC
                LIMIT 5
                """,
                user_id,
            )
            for row in rows:
                top_vods.append({
                    "series_id": row["vod_id_fk"],
                    "asset_nm": row["asset_nm"],
                    "poster_url": row["poster_url"],
                    "backdrop_url": row["backdrop_url"],
                })

            # cold start 보충: hybrid 부족분을 연령대 기반 cold_genre_detail VOD로 채움
            if len(top_vods) < 5:
                seen_ids = {v["series_id"] for v in top_vods}
                cold_rows = await conn.fetch(
                    f"""
                    SELECT tr.vod_id_fk, v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url
                    FROM {tag_table} tr
                    JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                    WHERE tr.user_id_fk = $1
                      AND tr.tag_category = 'cold_genre_detail'
                      AND v.backdrop_url IS NOT NULL
                      AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                    ORDER BY tr.vod_score DESC
                    LIMIT $2
                    """,
                    user_id,
                    5 - len(top_vods),
                )
                for row in cold_rows:
                    if row["vod_id_fk"] not in seen_ids:
                        top_vods.append({
                            "series_id": row["vod_id_fk"],
                            "asset_nm": row["asset_nm"],
                            "poster_url": row["poster_url"],
                            "backdrop_url": row["backdrop_url"],
                        })
    except Exception:
        pass

    # 2) patterns: tag_recommendation (top 5 태그 × top 10 VOD)
    #    - 배우 태그 + TV 연예/오락: 에피소드 단위 유지 (cast_guest 게스트 출연)
    #    - 그 외: series_nm 기준 중복 제거
    patterns = []
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT tr.tag_category, tr.tag_value, tr.tag_rank,
                       tr.tag_affinity, tr.vod_id_fk, tr.vod_rank, tr.vod_score,
                       v.series_nm, v.asset_nm, v.poster_url, v.ct_cl
                FROM {tag_table} tr
                JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                WHERE tr.user_id_fk = $1
                  AND tr.tag_category IN ('genre_detail', 'director', 'actor_lead', 'actor_guest', 'cold_genre_detail')
                  AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                ORDER BY tr.tag_rank, tr.vod_rank
                """,
                user_id,
            )

        # cold_genre_detail 라벨에 필요한 유저 이름(해시 앞 5자)
        user_label = user_id[:5]

        # tag_rank별 그룹핑 + 조건부 중복 제거
        # cold_genre_detail은 개인화 태그 뒤에 배치하기 위해 rank 오프셋 적용
        grouped: dict[int, dict] = {}
        seen_per_rank: dict[int, set] = {}
        cold_offset = 100  # cold 태그 rank를 뒤로 밀기
        for r in rows:
            category = r["tag_category"]
            rank = r["tag_rank"] + (cold_offset if category == "cold_genre_detail" else 0)
            ct_cl = r["ct_cl"] or ""
            nm = r["series_nm"] or r["asset_nm"]
            if rank not in grouped:
                grouped[rank] = {
                    "pattern_rank": rank,
                    "pattern_reason": _make_reason(category, r["tag_value"], user_label),
                    "tag_category": category,
                    "vod_list": [],
                }
                seen_per_rank[rank] = set()

            # actor_guest/director + TV 연예/오락 → 에피소드 단위 (중복 제거 안함)
            is_actor_variety = (category in ("actor_guest", "director") and ct_cl == "TV 연예/오락")
            if not is_actor_variety:
                if nm in seen_per_rank[rank]:
                    continue
                seen_per_rank[rank].add(nm)

            grouped[rank]["vod_list"].append({
                "series_id": r["vod_id_fk"],
                "asset_nm": r["asset_nm"],
                "poster_url": r["poster_url"],
                "score": r["vod_score"],
            })

        # tag_category는 내부용이므로 응답에서 제거, rank 재번호
        patterns = []
        for idx, k in enumerate(sorted(grouped.keys()), 1):
            g = grouped[k]
            g.pop("tag_category", None)
            g["pattern_rank"] = idx
            patterns.append(g)
    except Exception:
        pass

    # 3) vector similarity: user_embedding meta부분(384D) vs vod_series_embedding (시리즈 대표)
    #    2-step: ① meta 벡터 추출 → ② vod_series_embedding과 코사인 유사도
    vector_pattern = None
    try:
        async with pool.acquire() as conn:
            # step 1: user_embedding에서 meta 파트(뒤 384차원) 추출
            await conn.execute("SET ivfflat.probes = 5")
            ue_row = await conn.fetchrow(
                "SELECT (embedding::real[])[513:896]::vector(384) AS meta_vec "
                "FROM public.user_embedding WHERE user_id_fk = $1",
                user_id,
            )
            if ue_row:
                # step 2: vod_series_embedding과 cosine 유사도 (시리즈 단위, 중복제거 불필요)
                vector_rows = await conn.fetch(
                    """
                    SELECT se.series_nm,
                           1 - (se.embedding <=> $1) AS similarity,
                           v.asset_nm, se.poster_url
                    FROM public.vod_series_embedding se
                    JOIN public.vod v ON v.full_asset_id = se.representative_vod_id
                    WHERE se.poster_url IS NOT NULL
                    ORDER BY se.embedding <=> $1
                    LIMIT 10
                    """,
                    ue_row["meta_vec"],
                )
                vod_list = []
                for r in vector_rows:
                    vod_list.append({
                        "series_id": r["series_nm"],
                        "asset_nm": r["asset_nm"],
                        "poster_url": r["poster_url"],
                        "score": round(float(r["similarity"]), 4),
                    })
                if vod_list:
                    next_rank = max((p["pattern_rank"] for p in patterns), default=0) + 1
                    vector_pattern = {
                        "pattern_rank": next_rank,
                        "pattern_reason": "나의 취향과 비슷한 콘텐츠",
                        "vod_list": vod_list,
                    }
    except Exception:
        pass

    if vector_pattern:
        patterns.append(vector_pattern)

    if top_vods or patterns:
        return {"top_vod": top_vods, "patterns": patterns, "source": "personalized"}

    # Fallback: popular 기반
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT pr.vod_id_fk, pr.score,
                       v.asset_nm, v.poster_url, v.backdrop_url
                FROM serving.popular_recommendation pr
                JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
                WHERE v.backdrop_url IS NOT NULL
                  AND (pr.expires_at IS NULL OR pr.expires_at > NOW())
                ORDER BY pr.score DESC
                LIMIT 10
                """,
            )

        if rows:
            top_vods = [
                {
                    "series_id": r["vod_id_fk"],
                    "asset_nm": r["asset_nm"],
                    "poster_url": r["poster_url"],
                    "backdrop_url": r["backdrop_url"],
                }
                for r in rows[:5]
            ]
            patterns = [{
                "pattern_rank": 1,
                "pattern_reason": "지금 인기 있는 콘텐츠",
                "vod_list": [
                    {
                        "series_id": r["vod_id_fk"],
                        "asset_nm": r["asset_nm"],
                        "poster_url": r["poster_url"],
                        "score": r["score"],
                    }
                    for r in rows[5:]
                ],
            }]
    except Exception:
        pass

    return {"top_vod": top_vods, "patterns": patterns, "source": "popular_fallback"}
