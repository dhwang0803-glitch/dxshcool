"""
감독/배우 선호 기반 추천 후처리

- ALS Top-K 결과 뒤에 최대 2개(감독 1 + 배우 1) 추가
- 트리거: 동일 감독 3편+ OR 동일 배우 3편+ 시청한 유저에게만 적용
- recommendation_type: COLLABORATIVE (ALS와 동일, DB 스키마 변경 없음)
- 후보 조건: 미시청 + 품질 필터(poster_url + vod_embedding) 통과 VOD
"""

import json
import logging
from collections import Counter

log = logging.getLogger(__name__)


def parse_cast(value: str) -> list:
    """
    cast_lead / cast_guest 컬럼 파싱.
    JSON 배열 '["현빈", "유지태"]' 또는 쉼표 구분 '정형돈, 데프콘' 양쪽 지원.
    """
    if not value:
        return []
    value = value.strip()
    if value.startswith("["):
        try:
            return [v.strip() for v in json.loads(value) if isinstance(v, str) and v.strip()]
        except Exception:
            pass
    return [v.strip() for v in value.split(",") if v.strip()]


def load_vod_content(conn) -> dict:
    """vod_id → {director, cast} 매핑 로드."""
    cur = conn.cursor()
    cur.execute("""
        SELECT full_asset_id, director, cast_lead, cast_guest
        FROM public.vod
        WHERE director IS NOT NULL OR cast_lead IS NOT NULL OR cast_guest IS NOT NULL
    """)
    vod_content = {}
    for vod_id, director, cast_lead, cast_guest in cur.fetchall():
        cast = list(set(parse_cast(cast_lead) + parse_cast(cast_guest)))
        vod_content[vod_id] = {
            "director": director.strip() if director else None,
            "cast": cast,
        }
    cur.close()
    log.info("VOD 콘텐츠 메타 로드: %d건", len(vod_content))
    return vod_content


def load_quality_vod_ids(conn) -> set:
    """poster_url + vod_embedding 둘 다 있는 품질 필터 통과 vod_id 셋."""
    cur = conn.cursor()
    cur.execute("""
        SELECT v.full_asset_id
        FROM public.vod v
        JOIN public.vod_embedding e ON v.full_asset_id = e.vod_id_fk
        WHERE v.poster_url IS NOT NULL
    """)
    result = {row[0] for row in cur.fetchall()}
    cur.close()
    log.info("품질 필터 통과 VOD: %d건", len(result))
    return result


def load_user_history_map(conn) -> dict:
    """user_id → [vod_id, ...] 전체 시청 이력 로드 (필터 없음)."""
    cur = conn.cursor()
    cur.execute("SELECT user_id_fk, vod_id_fk FROM public.watch_history")
    history_map = {}
    for user_id, vod_id in cur.fetchall():
        history_map.setdefault(user_id, []).append(vod_id)
    cur.close()
    log.info("유저 시청 이력 맵 로드: %d명", len(history_map))
    return history_map


def detect_preferences(user_history: list, vod_content: dict,
                        min_count: int = 3) -> dict:
    """
    유저 시청 이력에서 선호 감독/배우 감지.
    Returns: {"director": str or None, "actor": str or None}
    """
    director_counter = Counter()
    actor_counter = Counter()

    for vod_id in user_history:
        meta = vod_content.get(vod_id)
        if not meta:
            continue
        if meta["director"]:
            director_counter[meta["director"]] += 1
        for actor in meta["cast"]:
            actor_counter[actor] += 1

    top_dir = director_counter.most_common(1)
    top_act = actor_counter.most_common(1)

    return {
        "director": top_dir[0][0] if top_dir and top_dir[0][1] >= min_count else None,
        "actor":    top_act[0][0] if top_act and top_act[0][1] >= min_count else None,
    }


def build_indexes(vod_content: dict, quality_vod_ids: set) -> tuple:
    """
    역인덱스 사전 빌드 (O(|vod_content|) 1회 → 이후 O(1) 조회).
    Returns: (director_index, actor_index)
      director_index: {director_name: [vod_id, ...]} — 품질 필터 통과 VOD만
      actor_index:    {actor_name:    [vod_id, ...]} — 품질 필터 통과 VOD만
    """
    director_index = {}
    actor_index = {}
    for vod_id, meta in vod_content.items():
        if vod_id not in quality_vod_ids:
            continue
        if meta["director"]:
            director_index.setdefault(meta["director"], []).append(vod_id)
        for actor in meta["cast"]:
            actor_index.setdefault(actor, []).append(vod_id)
    log.info("역인덱스 빌드 완료 — 감독 %d명 / 배우 %d명",
             len(director_index), len(actor_index))
    return director_index, actor_index


def _find_candidate_from_index(index: dict, pref_value: str,
                                watched_set: set, already_recommended: set):
    """역인덱스에서 미시청 + 미추천 VOD 1개 반환. 없으면 None."""
    for vod_id in index.get(pref_value, []):
        if vod_id not in watched_set and vod_id not in already_recommended:
            return vod_id
    return None


def apply_content_boost(records: list, user_history_map: dict,
                        vod_content: dict, quality_vod_ids: set,
                        recommendation_type: str = "COLLABORATIVE",
                        min_count: int = 3) -> list:
    """
    ALS 추천 레코드 전체에 감독/배우 후처리 적용.

    Args:
        records: build_records() 결과 [{"user_id_fk", "vod_id_fk", "rank", "score", ...}]
        user_history_map: load_user_history_map() 결과
        vod_content: load_vod_content() 결과
        quality_vod_ids: load_quality_vod_ids() 결과
        recommendation_type: 저장할 recommendation_type 값
        min_count: 선호 감지 최소 시청 수

    Returns:
        후처리 적용된 레코드 리스트 (기존 + 추가분)
    """
    # 역인덱스 1회 빌드
    director_index, actor_index = build_indexes(vod_content, quality_vod_ids)

    # user_id별로 그룹핑
    user_recs = {}
    for rec in records:
        user_recs.setdefault(rec["user_id_fk"], []).append(rec)

    boosted_count = 0
    result = []

    for user_id, recs in user_recs.items():
        user_history = user_history_map.get(user_id, [])
        prefs = detect_preferences(user_history, vod_content, min_count=min_count)

        if not prefs["director"] and not prefs["actor"]:
            result.extend(recs)
            continue

        watched_set = set(user_history)
        already_recommended = {r["vod_id_fk"] for r in recs}
        current_rank = max(r["rank"] for r in recs)
        extra = []

        for pref_key, index in (("director", director_index), ("actor", actor_index)):
            pref_value = prefs[pref_key]
            if not pref_value:
                continue
            candidate = _find_candidate_from_index(
                index, pref_value, watched_set, already_recommended
            )
            if candidate:
                current_rank += 1
                extra.append({
                    "user_id_fk": user_id,
                    "vod_id_fk": candidate,
                    "rank": current_rank,
                    "score": 0.0,
                    "recommendation_type": recommendation_type,
                })
                already_recommended.add(candidate)

        result.extend(recs)
        result.extend(extra)
        if extra:
            boosted_count += 1

    log.info("콘텐츠 후처리 적용 유저: %d명 / 전체 %d명", boosted_count, len(user_recs))
    return result
