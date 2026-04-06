from app.services.base_service import BaseService
from app.services.rec_sentence_service import get_segment_id

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

_TAG_LABEL = {
    "genre": "추천 인기 {value}",
    "cold_genre_detail": "{user}님이 좋아할만한 {value} 시리즈",
}

_REC_REASON_BY_CATEGORY = {
    "actor_lead": "{value} 님 작품",
    "actor_guest": "{value} 배우 출연작",
    "director": "{value} 감독 작품",
    "genre": "{value} 장르",
    "genre_detail": "{value} 장르",
    "cold_genre_detail": "{value} 장르",
}


def _clean_genre_detail(raw: str | None) -> str | None:
    if not raw or not raw.strip():
        return None
    val = raw.strip()
    if val.startswith("(HD)"):
        return None
    if val in _GENRE_BLACKLIST:
        return None
    parts = [p.strip() for p in val.replace(", ", ",").split(",") if p.strip()]
    return parts[0] if parts else None


class HomeService(BaseService):
    async def get_banner(self) -> list[dict]:
        """히어로 배너: popular score top 5 (시리즈 중복 제거)."""
        rows = await self.query(
            """
            SELECT pr.vod_id_fk, pr.score,
                   v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url, v.ct_cl
            FROM serving.popular_recommendation pr
            JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
            WHERE v.backdrop_url IS NOT NULL
              AND v.poster_url IS NOT NULL
              AND (pr.expires_at IS NULL OR pr.expires_at > NOW())
              AND v.release_date >= NOW() - INTERVAL '2 years'
            ORDER BY pr.score DESC
            LIMIT 15
            """,
        )

        deduped = self.deduplicate_series(rows, limit=5)
        return [
            {
                "series_nm": r["series_nm"] or r["asset_nm"],
                "title": r["series_nm"] or r["asset_nm"],
                "poster_url": r["poster_url"],
                "backdrop_url": r["backdrop_url"],
                "category": r["ct_cl"],
                "score": r["score"],
            }
            for r in deduped
        ]

    async def get_sections(self) -> list[dict]:
        """CT_CL 4종 × Top 20 인기 추천."""
        rows = await self.query(
            """
            SELECT pr.ct_cl, pr.rank, pr.score, pr.vod_id_fk,
                   v.series_nm, v.asset_nm, v.poster_url
            FROM serving.popular_recommendation pr
            JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
            WHERE v.poster_url IS NOT NULL
            ORDER BY pr.ct_cl, pr.rank
            """,
        )

        sections: dict[str, list] = {}
        for r in rows:
            ct = r["ct_cl"]
            if ct not in sections:
                sections[ct] = []
            sections[ct].append({
                "series_nm": r["series_nm"] or r["asset_nm"],
                "title": r["series_nm"] or r["asset_nm"],
                "poster_url": r["poster_url"],
                "score": r["score"],
                "rank": r["rank"],
            })

        return [{"ct_cl": ct, "vod_list": vods} for ct, vods in sections.items()]

    async def get_personalized_sections(self, user_id: str) -> list[dict] | None:
        """홈 개인화 섹션: 태그 배너 + vector 배너 + TOP10."""
        is_test = await self.is_test_user(user_id)
        tag_table = "serving.tag_recommendation_test" if is_test else "serving.tag_recommendation"
        sections: list[dict] = []

        async with await self.acquire() as conn:
            # 1) 태그 배너
            rows = await conn.fetch(
                f"""
                SELECT tr.tag_category, tr.tag_value, tr.tag_rank,
                       tr.vod_id_fk, tr.vod_rank, tr.vod_score,
                       v.series_nm, v.asset_nm, v.poster_url
                FROM {tag_table} tr
                JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                WHERE tr.user_id_fk = $1
                  AND (tr.tag_category = 'genre'
                       OR (tr.tag_category = 'cold_genre_detail' AND tr.tag_rank <= 3))
                  AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                  AND v.poster_url IS NOT NULL
                ORDER BY
                    CASE WHEN tr.tag_category = 'genre' THEN 0 ELSE 1 END,
                    tr.tag_rank, tr.vod_rank
                """,
                user_id,
            )

            user_label = user_id[:5]
            grouped: dict[int, dict] = {}
            seen_vods: set[str] = set()
            seq = 0
            for r in rows:
                cat = r["tag_category"]
                raw_rank = r["tag_rank"]
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

            # 2) vector 배너
            try:
                await conn.execute("SET ivfflat.probes = 5")
                ue_row = await conn.fetchrow(
                    "SELECT (embedding::real[])[513:896]::vector(384) AS meta_vec "
                    "FROM public.user_embedding WHERE user_id_fk = $1",
                    user_id,
                )
                if ue_row:
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
                    top_genres = sorted(
                        ((g, v) for g, v in genre_groups.items() if len(v) >= 10),
                        key=lambda x: -len(x[1]),
                    )[:2]
                    # 벡터 배너 VOD에 근거 시청 VOD 매칭
                    all_vector_nms = [
                        v["series_nm"]
                        for _, vods in top_genres
                        for v in vods
                    ]
                    try:
                        source_map = await self.find_source_vods(
                            conn, user_id, all_vector_nms,
                        )
                    except Exception:
                        source_map = {}
                    for genre, vods in top_genres:
                        if vods:
                            for v in vods:
                                v["source_title"] = source_map.get(v["series_nm"])
                            sections.append({
                                "genre": f"나의 취향과 비슷한 {genre}",
                                "vod_list": vods,
                            })
            except Exception:
                pass

            # 3) TOP10
            try:
                segment_id = await get_segment_id(conn, user_id)
                top10_rows = await conn.fetch(
                    f"""
                    SELECT tr.vod_id_fk, tr.vod_score,
                           tr.tag_category, tr.tag_value,
                           v.series_nm, v.asset_nm, v.poster_url,
                           rs.rec_sentence
                    FROM {tag_table} tr
                    JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                    LEFT JOIN LATERAL (
                        SELECT rs2.rec_sentence
                        FROM serving.rec_sentence rs2
                        JOIN public.vod v2 ON rs2.vod_id_fk = v2.full_asset_id
                        WHERE v2.series_nm = v.series_nm
                          AND rs2.segment_id = $2
                        LIMIT 1
                    ) rs ON true
                    WHERE tr.user_id_fk = $1
                      AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                      AND v.poster_url IS NOT NULL
                    ORDER BY tr.vod_score DESC
                    LIMIT 50
                    """,
                    user_id, segment_id,
                )
                top10_vods = self.deduplicate_series(top10_rows, limit=10)
                for i, v in enumerate(top10_vods, 1):
                    v["rank"] = i
                    cat = v.pop("tag_category", None)
                    val = v.pop("tag_value", None)
                    tpl = _REC_REASON_BY_CATEGORY.get(cat)
                    v["rec_reason"] = tpl.format(value=val) if tpl and val else "취향 기반 추천"
                if top10_vods:
                    sections.append({
                        "genre": f"{user_label}님만을 위한 추천 시리즈 TOP10",
                        "vod_list": top10_vods,
                    })
            except Exception:
                pass

        return sections if sections else None


home_service = HomeService()

# 하위 호환
get_banner = home_service.get_banner
get_sections = home_service.get_sections
get_personalized_sections = home_service.get_personalized_sections
