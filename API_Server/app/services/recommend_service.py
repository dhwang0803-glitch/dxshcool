"""개인화 추천 서비스 — hybrid_recommendation + tag_recommendation 기반."""

from pathlib import Path

import yaml

from app.services.base_service import BaseService
from app.services.rec_sentence_service import get_rec_sentences, get_segment_id

# ── 배너 문구 설정 (config/banner_templates.yaml) ─────────
_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "banner_templates.yaml"

_FALLBACK_TEMPLATES = {
    "genre_detail": "즐겨 보는 {value} 시리즈",
    "director": "{value} 감독 작품 모아보기",
    "actor_lead": "{value} 출연 시리즈 모아보기",
    "actor_guest": "{value} 출연작 모아보기",
    "cold_genre_detail": "{user}님을 위한 {value} 추천",
}


_FALLBACK_VALUE_OVERRIDES = {
    "genre_detail": {"드라마틱": "드라마틱한 영화"},
}


def _load_banner_config() -> dict:
    try:
        with open(_CONFIG_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


_BANNER_CFG = _load_banner_config()


def _override_value(tag_category: str, tag_value: str) -> str:
    """혼동 방지 값 변환 (e.g. 드라마틱 → 드라마틱한 영화)."""
    overrides = _BANNER_CFG.get("value_overrides", _FALLBACK_VALUE_OVERRIDES).get(tag_category, {})
    return overrides.get(tag_value, tag_value)


def _make_reason(
    tag_category: str, tag_value: str,
    user_label: str = "", segment_id: int | None = None,
) -> str:
    """세그먼트별 개인화 배너 문구 생성."""
    templates = _BANNER_CFG.get("templates", {})
    seg_tpl = templates.get(segment_id, {}) if segment_id is not None else {}
    default_tpl = templates.get("default", _FALLBACK_TEMPLATES)

    tpl = seg_tpl.get(tag_category) or default_tpl.get(
        tag_category, "{value} 관련 콘텐츠를 즐겨 보셨어요"
    )
    display_value = _override_value(tag_category, tag_value)
    return tpl.format(value=display_value, user=user_label)


class RecommendService(BaseService):
    async def get_recommendations(self, user_id: str) -> dict:
        is_test = await self.is_test_user(user_id)
        hybrid_table = "serving.hybrid_recommendation_test" if is_test else "serving.hybrid_recommendation"
        tag_table = "serving.tag_recommendation_test" if is_test else "serving.tag_recommendation"

        # segment_id 조회 (배너 문구 개인화 + rec_sentence 조회용)
        segment_id = None
        try:
            async with await self.acquire() as conn:
                segment_id = await get_segment_id(conn, user_id)
        except Exception:
            pass

        # 1) top_vods: hybrid score 내림차순 top 10 (시리즈 중복 제거)
        top_vods = []
        youtube_filter = "AND v.youtube_video_id IS NOT NULL AND v.youtube_video_id != ''" if is_test else ""
        try:
            async with await self.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT r.vod_id_fk, v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url
                    FROM {hybrid_table} r
                    JOIN public.vod v ON r.vod_id_fk = v.full_asset_id
                    WHERE r.user_id_fk = $1
                      AND v.backdrop_url IS NOT NULL
                      AND v.poster_url IS NOT NULL
                      {youtube_filter}
                      AND (r.expires_at IS NULL OR r.expires_at > NOW())
                    ORDER BY r.score DESC
                    LIMIT 30
                    """,
                    user_id,
                )
                seen_series = set()
                for row in rows:
                    sid = row["series_nm"] or row["asset_nm"]
                    if sid in seen_series:
                        continue
                    seen_series.add(sid)
                    top_vods.append({
                        "vod_id": row["vod_id_fk"],
                        "series_id": sid,
                        "asset_nm": sid,
                        "poster_url": row["poster_url"],
                        "backdrop_url": row["backdrop_url"],
                    })
                    if len(top_vods) >= 10:
                        break

                # cold start 보충
                if len(top_vods) < 10:
                    seen_ids = {v["series_id"] for v in top_vods}
                    cold_rows = await conn.fetch(
                        f"""
                        SELECT tr.vod_id_fk, v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url
                        FROM {tag_table} tr
                        JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                        WHERE tr.user_id_fk = $1
                          AND tr.tag_category = 'cold_genre_detail'
                          AND v.backdrop_url IS NOT NULL
                          AND v.poster_url IS NOT NULL
                          {youtube_filter}
                          AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                        ORDER BY tr.vod_score DESC
                        LIMIT 30
                        """,
                        user_id,
                    )
                    need = 10 - len(top_vods)
                    for row in cold_rows:
                        sid = row["series_nm"] or row["asset_nm"]
                        if sid not in seen_ids:
                            seen_ids.add(sid)
                            top_vods.append({
                                "vod_id": row["vod_id_fk"],
                                "series_id": sid,
                                "asset_nm": sid,
                                "poster_url": row["poster_url"],
                                "backdrop_url": row["backdrop_url"],
                            })
                            need -= 1
                            if need <= 0:
                                break
        except Exception:
            pass

        # 2) patterns: tag_recommendation (top 5 태그 × top 10 VOD)
        patterns = []
        try:
            async with await self.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT tr.tag_category, tr.tag_value, tr.tag_rank,
                           tr.tag_affinity, tr.vod_id_fk, tr.vod_rank, tr.vod_score,
                           v.series_nm, v.asset_nm, v.poster_url, v.ct_cl,
                           vt.confidence AS vod_confidence
                    FROM {tag_table} tr
                    JOIN public.vod v ON tr.vod_id_fk = v.full_asset_id
                    LEFT JOIN public.vod_tag vt
                         ON vt.vod_id_fk = tr.vod_id_fk
                        AND vt.tag_category = tr.tag_category
                        AND vt.tag_value = tr.tag_value
                    WHERE tr.user_id_fk = $1
                      AND (tr.tag_category IN ('genre_detail', 'director', 'actor_lead', 'actor_guest')
                           OR (tr.tag_category = 'cold_genre_detail' AND tr.tag_rank >= 4))
                      AND v.poster_url IS NOT NULL
                      AND (tr.expires_at IS NULL OR tr.expires_at > NOW())
                    ORDER BY tr.tag_rank, tr.vod_rank
                    """,
                    user_id,
                )

            user_label = user_id[:5]
            cold_offset = 100
            grouped: dict[tuple, dict] = {}
            seen_per_group: dict[tuple, set] = {}
            for r in rows:
                category = r["tag_category"]
                tag_value = r["tag_value"]
                rank = r["tag_rank"] + (cold_offset if category == "cold_genre_detail" else 0)
                ct_cl = r["ct_cl"] or ""
                nm = r["series_nm"] or r["asset_nm"]
                group_key = (category, tag_value)
                if group_key not in grouped:
                    grouped[group_key] = {
                        "sort_rank": rank,
                        "tag_affinity": float(r["tag_affinity"] or 0),
                        "pattern_reason": _make_reason(category, tag_value, user_label, segment_id),
                        "vod_list": [],
                    }
                    seen_per_group[group_key] = set()

                is_actor_variety = (category == "actor_guest" and ct_cl == "TV 연예/오락")
                if not is_actor_variety:
                    if nm in seen_per_group[group_key]:
                        continue
                    seen_per_group[group_key].add(nm)

                grouped[group_key]["vod_list"].append({
                    "series_id": r["series_nm"] or r["asset_nm"],
                    "asset_nm": r["asset_nm"] if is_actor_variety else nm,
                    "poster_url": r["poster_url"],
                    "score": r["vod_score"],
                    "confidence": float(r["vod_confidence"] or 0),
                })

            patterns = []
            for idx, (_, g) in enumerate(
                sorted(grouped.items(), key=lambda x: x[1]["sort_rank"]), 1
            ):
                g.pop("sort_rank", None)
                g["pattern_rank"] = idx
                patterns.append(g)
        except Exception:
            pass

        # 3) vector similarity — 파이프라인 vod_recommendation VISUAL_SIMILARITY 결과 사용
        rec_table = "serving.vod_recommendation_test" if is_test else "serving.vod_recommendation"
        vector_pattern = None
        try:
            async with await self.acquire() as conn:
                vector_rows = await conn.fetch(
                    f"""
                    SELECT vr.vod_id_fk, vr.score, vr.source_vod_id,
                           v.series_nm, v.asset_nm, v.poster_url,
                           src.asset_nm AS source_title
                    FROM {rec_table} vr
                    JOIN public.vod v ON v.full_asset_id = vr.vod_id_fk
                    LEFT JOIN public.vod src ON src.full_asset_id = vr.source_vod_id
                    WHERE vr.user_id_fk = $1
                      AND vr.recommendation_type = 'VISUAL_SIMILARITY'
                      AND v.poster_url IS NOT NULL
                      AND (vr.expires_at IS NULL OR vr.expires_at > NOW())
                    ORDER BY vr.score DESC
                    LIMIT 20
                    """,
                    user_id,
                )
                # 시리즈 중복 제거
                seen_series = set()
                vod_list = []
                for r in vector_rows:
                    sid = r["series_nm"] or r["asset_nm"]
                    if sid in seen_series:
                        continue
                    seen_series.add(sid)
                    vod_list.append({
                        "series_id": sid,
                        "asset_nm": sid,
                        "poster_url": r["poster_url"],
                        "score": round(float(r["score"]), 4),
                        "source_title": r["source_title"],
                    })
                    if len(vod_list) >= 10:
                        break

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
            if top_vods:
                try:
                    async with await self.acquire() as conn:
                        if segment_id is None:
                            segment_id = await get_segment_id(conn, user_id)
                        vod_ids = [v["vod_id"] for v in top_vods]
                        rec_map = await get_rec_sentences(conn, vod_ids, segment_id)
                    for v in top_vods:
                        v["rec_sentence"] = rec_map.get(v["vod_id"])
                except Exception:
                    pass
            return {"top_vod": top_vods, "patterns": patterns, "source": "personalized"}

        # Fallback: popular
        try:
            async with await self.acquire() as conn:
                rows = await conn.fetch(
                    f"""
                    SELECT pr.vod_id_fk, pr.score,
                           v.series_nm, v.asset_nm, v.poster_url, v.backdrop_url
                    FROM serving.popular_recommendation pr
                    JOIN public.vod v ON pr.vod_id_fk = v.full_asset_id
                    WHERE v.backdrop_url IS NOT NULL
                      AND v.poster_url IS NOT NULL
                      {youtube_filter}
                      AND (pr.expires_at IS NULL OR pr.expires_at > NOW())
                    ORDER BY pr.score DESC
                    LIMIT 10
                    """,
                )

            if rows:
                top_vods = [
                    {
                        "vod_id": r["vod_id_fk"],
                        "series_id": r["series_nm"] or r["asset_nm"],
                        "asset_nm": r["series_nm"] or r["asset_nm"],
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
                            "series_id": r["series_nm"] or r["asset_nm"],
                            "asset_nm": r["series_nm"] or r["asset_nm"],
                            "poster_url": r["poster_url"],
                            "score": r["score"],
                        }
                        for r in rows[5:]
                    ],
                }]
        except Exception:
            pass

        return {"top_vod": top_vods, "patterns": patterns, "source": "popular_fallback"}


recommend_service = RecommendService()

# 하위 호환
get_recommendations = recommend_service.get_recommendations
