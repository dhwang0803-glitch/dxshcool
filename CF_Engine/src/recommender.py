"""
STEP 3: ALS 출력 → DB 저장 형식 변환

시리즈 중복 제거:
- TV 연예/오락 → 에피소드 단위 유지 (게스트 출연이 회차별 다름)
- 그 외 → series_nm 기준 중복 제거 (같은 시리즈 에피소드 중 최고 score 1건만)
"""

import logging

log = logging.getLogger(__name__)

# 에피소드 단위 유지 대상 ct_cl (시리즈 중복 제거 제외)
_EPISODE_LEVEL_CT_CL = frozenset(["TV 연예/오락"])


def load_vod_series_map(conn) -> dict[str, tuple[str, str]]:
    """vod_id → (series_nm, ct_cl) 매핑 로드."""
    cur = conn.cursor()
    cur.execute("SELECT full_asset_id, series_nm, ct_cl FROM public.vod")
    vod_map = {}
    for vod_id, series_nm, ct_cl in cur.fetchall():
        vod_map[vod_id] = (series_nm or vod_id, ct_cl or "")
    cur.close()
    log.info("VOD 시리즈 매핑 로드: %d건", len(vod_map))
    return vod_map


def build_records(user_ids, item_indices, scores,
                  user_decoder: dict, item_decoder: dict,
                  recommendation_type: str = "CF",
                  top_k: int = 20,
                  vod_series_map: dict | None = None) -> list[dict]:
    """
    ALS 추천 결과를 serving.vod_recommendation 저장 형식으로 변환.

    vod_series_map이 제공되면 시리즈 중복 제거 적용:
    - TV 연예/오락: 에피소드 단위 유지
    - 그 외: series_nm 기준 중복 제거 (최고 score 1건)

    Returns:
        List[dict]: user_id_fk, vod_id_fk, rank, score, recommendation_type
    """
    records = []
    skipped = 0
    for uid, item_row, score_row in zip(user_ids, item_indices, scores):
        user_id_fk = user_decoder[uid]
        seen_series: set[str] = set()
        rank = 0
        for iid, score in zip(item_row, score_row):
            vod_id = item_decoder[iid]

            # 시리즈 중복 제거
            if vod_series_map is not None:
                series_nm, ct_cl = vod_series_map.get(vod_id, (vod_id, ""))
                if ct_cl not in _EPISODE_LEVEL_CT_CL:
                    if series_nm in seen_series:
                        skipped += 1
                        continue
                    seen_series.add(series_nm)

            rank += 1
            if rank > top_k:
                break
            records.append({
                "user_id_fk": user_id_fk,
                "vod_id_fk": vod_id,
                "rank": rank,
                "score": float(score),
                "recommendation_type": recommendation_type,
            })
    log.info("레코드 생성 완료: %d건 (시리즈 중복 제거: %d건 스킵)", len(records), skipped)
    return records
