"""
STEP 3: ALS 출력 → DB 저장 형식 변환
"""

import logging
import numpy as np

log = logging.getLogger(__name__)


def build_records(user_ids, item_indices, scores,
                  user_decoder: dict, item_decoder: dict,
                  recommendation_type: str = "CF") -> list[dict]:
    """
    ALS 추천 결과를 serving.vod_recommendation 저장 형식으로 변환.

    Returns:
        List[dict]: user_id_fk, vod_id_fk, rank, score, recommendation_type
    """
    records = []
    for uid, item_row, score_row in zip(user_ids, item_indices, scores):
        user_id_fk = user_decoder[uid]
        for rank, (iid, score) in enumerate(zip(item_row, score_row), start=1):
            records.append({
                "user_id_fk": user_id_fk,
                "vod_id_fk": item_decoder[iid],
                "rank": rank,
                "score": float(score),
                "recommendation_type": recommendation_type,
            })
    log.info("레코드 생성 완료: %d건", len(records))
    return records
