from app.services.db import get_pool

# genre_detail 채널/패키지명 필터 (Hybrid_Layer/src/tag_builder.py와 동기화)
_GENRE_BLACKLIST = frozenset({
    "무비n시리즈", "만화동산", "제이박스", "게임애니팩토리",
    "캐치온디맨드", "캐치온라이트", "핑크퐁TV", "EBS키즈",
    "투니버스월정액", "IHQ무제한", "MBCevery1", "MBN", "TV조선",
    "KBSN", "채널A", "중화TV", "캐리TV", "BBC키즈", "아이들나라",
    "tvN드라마", "JTBC시사교양", "JTBC드라마", "JTBC4",
    "지상파구작", "레드무비", "테마영화관", "PLAYY영화",
    "양천 사랑방", "케이블 연예오락",
    "MBC구작", "SBS구작", "KBS구작", "CJENM구작", "JTBC구작",
    "정보미상", "무료영화", "기타", "추천시리즈", "시리즈",
    "동요-동화", "영어-놀이학습", "뮤직비디오",
})


def _clean_genre_detail(raw: str | None) -> str | None:
    """genre_detail에서 채널/패키지명 제거. None 반환 시 ct_cl fallback."""
    if not raw or not raw.strip():
        return None
    val = raw.strip()
    if val.startswith("(HD)"):
        return None
    if val in _GENRE_BLACKLIST:
        return None
    # TMDB 복합 장르 → 첫 번째 장르만 사용 (그룹핑 키)
    parts = [p.strip() for p in val.replace(", ", ",").split(",") if p.strip()]
    return parts[0] if parts else None


async def _is_test_user(pool, user_id: str) -> bool:
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT is_test FROM public."user" WHERE sha2_hash = $1',
                user_id,
            )
        return bool(row and row["is_test"])
    except Exception:
        return False


async def get_banner(user_id: str | None = None) -> list[dict]:
    """히어로 배너 2단 구조.

    1단: popular_recommendation score 내림차순 top 5 — 항상 (비개인화 히어로)
    2단: hybrid_recommendation top 10 — 로그인 유저 (하단 개인화, seen 중복 제거)
    비로그인 시 1단만 반환.
    """
    pool = await get_pool()
    seen: set[str] = set()
    items: list[dict] = []

    def _append_rows(rows):
        for r in rows:
            nm = r["series_nm"] or r["asset_nm"]
            if nm in seen:
                continue
            seen.add(nm)
            items.append({
                "series_nm": nm,
                "title": r["asset_nm"],
                "poster_url": r["poster_url"],
                "backdrop_url": r["backdrop_url"],
                "category": r["ct_cl"],
                "score": r["score"],
            })

    async with pool.acquire() as conn:
        # 1단: popular_recommendation 히어로 top 5 (항상)
        rows = await conn.fetch(
            """
            SELECT pr.vod_id_fk, pr.score,
                   v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url, v.ct_cl
            FROM serving.popular_recommendation pr
            JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
            WHERE pr.expires_at IS NULL OR pr.expires_at > NOW()
            ORDER BY pr.score DESC
            LIMIT 5
            """,
        )
        _append_rows(rows)

        # 2단: hybrid_recommendation 개인화 top 10 (로그인 유저만)
        if user_id:
            is_test = await _is_test_user(pool, user_id)
            hybrid_table = "serving.hybrid_recommendation_test" if is_test else "serving.hybrid_recommendation"
            try:
                rows = await conn.fetch(
                    f"""
                    SELECT r.vod_id_fk, r.score,
                           v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url, v.ct_cl
                    FROM {hybrid_table} r
                    JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                    WHERE r.user_id_fk = $1
                      AND (r.expires_at IS NULL OR r.expires_at > NOW())
                    ORDER BY r.rank
                    LIMIT 10
                    """,
                    user_id,
                )
                _append_rows(rows)
            except Exception:
                pass

    return items


async def get_sections() -> list[dict]:
    """CT_CL 4종 × Top 20 인기 추천."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT pr.ct_cl, pr.rank, pr.score, pr.vod_id_fk,
                   v.series_nm, v.asset_nm, v.poster_url
            FROM serving.popular_recommendation pr
            JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
            ORDER BY pr.ct_cl, pr.rank
            """
        )

    sections: dict[str, list] = {}
    for r in rows:
        ct = r["ct_cl"]
        if ct not in sections:
            sections[ct] = []
        sections[ct].append(
            {
                "series_nm": r["series_nm"] or r["asset_nm"],
                "title": r["asset_nm"],
                "poster_url": r["poster_url"],
                "score": r["score"],
                "rank": r["rank"],
            }
        )

    return [{"ct_cl": ct, "vod_list": vods} for ct, vods in sections.items()]


_TAG_LABEL = {
    "genre": "추천 인기 {value}",
    "cold_genre_detail": "{user}님이 좋아할만한 {value} 시리즈",
}


async def get_personalized_sections(user_id: str) -> list[dict]:
    """홈 개인화 섹션: 태그 배너 + vector 배너 + TOP10. 비로그인 시 None."""
    pool = await get_pool()
    is_test = await _is_test_user(pool, user_id)
    tag_table = "serving.tag_recommendation_test" if is_test else "serving.tag_recommendation"
    sections: list[dict] = []

    async with pool.acquire() as conn:
        # ── 1) 태그 배너: genre + cold_genre_detail (cold start fallback) ──
        rows = await conn.fetch(
            f"""
            SELECT tr.tag_category, tr.tag_value, tr.tag_rank,
                   tr.vod_id_fk, tr.vod_rank, tr.vod_score,
                   v.series_nm, v.asset_nm, v.poster_url
            FROM {tag_table} tr
            JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
            WHERE tr.user_id_fk = $1
              AND tr.tag_category IN ('genre', 'cold_genre_detail')
              AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
            ORDER BY
                CASE WHEN tr.tag_category = 'genre' THEN 0 ELSE 1 END,
                tr.tag_rank, tr.vod_rank
            """,
            user_id,
        )

        user_label = user_id[:5]
        grouped: dict[int, dict] = {}
        seen_vods: set[str] = set()
        seq = 0  # 순차 rank 부여
        for r in rows:
            cat = r["tag_category"]
            raw_rank = r["tag_rank"]
            # cold 태그는 genre 뒤에 오도록 offset
            rank_key = raw_rank if cat == "genre" else 100 + raw_rank
            nm = r["series_nm"] or r["asset_nm"]
            if nm in seen_vods:
                continue
            seen_vods.add(nm)
            if rank_key not in grouped:
                seq += 1
                tpl = _TAG_LABEL.get(cat, "{value}")
                label = tpl.format(value=r["tag_value"], user=user_label)
                grouped[rank_key] = {
                    "genre": label,
                    "view_ratio": max(100 - (seq - 1) * 15, 40),
                    "vod_list": [],
                }
            grouped[rank_key]["vod_list"].append({
                "series_nm": nm,
                "asset_nm": r["asset_nm"],
                "poster_url": r["poster_url"],
            })
        sections.extend(grouped[k] for k in sorted(grouped.keys()))

        # ── 2) vector 배너: 취향 유사도 top → 장르별 2그룹 ──
        try:
            await conn.execute("SET ivfflat.probes = 5")
            ue_row = await conn.fetchrow(
                "SELECT (embedding::real[])[513:896]::vector(384) AS meta_vec "
                "FROM public.user_embedding WHERE user_id_fk = $1",
                user_id,
            )
            if ue_row:
                # vod_series_embedding 사용: 시리즈당 1건이므로 에피소드 중복 없음
                vector_rows = await conn.fetch(
                    """
                    SELECT se.series_nm,
                           1 - (se.embedding <=> $1) AS similarity,
                           se.poster_url, se.ct_cl,
                           v.asset_nm, v.genre_detail
                    FROM public.vod_series_embedding se
                    JOIN public.vod v ON v.full_asset_id = se.representative_vod_id
                    WHERE se.poster_url IS NOT NULL
                    ORDER BY se.embedding <=> $1
                    LIMIT 60
                    """,
                    ue_row["meta_vec"],
                )
                # 장르별 그룹핑 (genre_detail 정제 → ct_cl fallback)
                genre_groups: dict[str, list] = {}
                for r in vector_rows:
                    nm = r["series_nm"]
                    if nm in seen_vods:
                        continue
                    genre = _clean_genre_detail(r["genre_detail"]) or r["ct_cl"] or "콘텐츠"
                    if genre not in genre_groups:
                        genre_groups[genre] = []
                    if len(genre_groups[genre]) < 10:
                        seen_vods.add(nm)
                        genre_groups[genre].append({
                            "series_nm": nm,
                            "asset_nm": r["asset_nm"],
                            "poster_url": r["poster_url"],
                            "score": round(float(r["similarity"]), 4),
                        })
                # 상위 2개 장르 그룹 (VOD 10개 이상만, VOD 수 많은 순)
                top_genres = sorted(
                    ((g, v) for g, v in genre_groups.items() if len(v) >= 10),
                    key=lambda x: -len(x[1]),
                )[:2]
                for genre, vods in top_genres:
                    if vods:
                        sections.append({
                            "genre": f"나의 취향과 비슷한 {genre}",
                            "vod_list": vods,
                        })
        except Exception:
            pass

        # ── 3) TOP10: 전체 태그 score 상위 10 + 추천 문구 ──
        try:
            top10_rows = await conn.fetch(
                f"""
                SELECT tr.vod_id_fk, tr.vod_score,
                       v.series_nm, v.asset_nm, v.poster_url,
                       rs.rec_reason, rs.rec_sentence
                FROM {tag_table} tr
                JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                LEFT JOIN serving.rec_sentence rs
                    ON rs.user_id_fk = tr.user_id_fk AND rs.vod_id_fk = tr.vod_id_fk
                    AND (rs.expires_at IS NULL OR rs.expires_at > NOW())
                WHERE tr.user_id_fk = $1
                  AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                ORDER BY tr.vod_score DESC
                LIMIT 50
                """,
                user_id,
            )
            seen_top10: set[str] = set()
            top10_vods: list[dict] = []
            for r in top10_rows:
                nm = r["series_nm"] or r["asset_nm"]
                if nm in seen_top10:
                    continue
                seen_top10.add(nm)
                top10_vods.append({
                    "series_nm": nm,
                    "asset_nm": r["asset_nm"],
                    "poster_url": r["poster_url"],
                    "rank": len(top10_vods) + 1,
                    "rec_reason": r["rec_reason"],
                    "rec_sentence": r["rec_sentence"],
                })
                if len(top10_vods) >= 10:
                    break
            if top10_vods:
                user_label = user_id[:5]
                sections.append({
                    "genre": f"{user_label}님만을 위한 추천 시리즈 TOP10",
                    "vod_list": top10_vods,
                })
        except Exception:
            pass

    return sections if sections else None
