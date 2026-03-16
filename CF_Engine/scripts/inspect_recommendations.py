"""
추천 결과 육안 검증
- 유저별 시청 이력과 CF 추천 결과를 나란히 출력
- 추천이 시청 이력과 연관성 있는지 눈으로 확인

실행: python scripts/inspect_recommendations.py
      python scripts/inspect_recommendations.py --users 10 --top-k 10
"""

import sys
import argparse
import logging
from pathlib import Path

import yaml
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from src.data_loader import get_conn, load_matrix
from src.als_model import train

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_vod_titles(conn, vod_ids: list) -> dict:
    """vod_id → asset_nm (VOD 제목) 매핑 로드"""
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(vod_ids))
    cur.execute(
        f"SELECT full_asset_id, asset_nm FROM public.vod WHERE full_asset_id IN ({placeholders})",
        vod_ids,
    )
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return result


def load_watch_history(conn, user_ids: list) -> dict:
    """특정 유저들의 시청 이력 로드 (completion_rate 높은 순)"""
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(user_ids))
    cur.execute(
        f"""
        SELECT user_id_fk, vod_id_fk, completion_rate
        FROM watch_history
        WHERE user_id_fk IN ({placeholders})
          AND completion_rate IS NOT NULL
        ORDER BY user_id_fk, completion_rate DESC
        """,
        user_ids,
    )
    history = {}
    for user_id, vod_id, rate in cur.fetchall():
        history.setdefault(user_id, []).append((vod_id, rate))
    cur.close()
    return history


def sample_users(mat, user_decoder: dict, n: int, min_history: int = 5) -> list:
    """시청 이력이 충분한 유저를 랜덤 샘플링"""
    candidates = [
        uid for uid in range(mat.shape[0])
        if mat.getrow(uid).nnz >= min_history
    ]
    sampled = np.random.choice(candidates, size=min(n, len(candidates)), replace=False)
    return [user_decoder[uid] for uid in sampled]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--users", type=int, default=5, help="검증할 유저 수")
    parser.add_argument("--top-k", type=int, default=10, help="추천 결과 개수")
    parser.add_argument("--min-history", type=int, default=5, help="최소 시청 이력 수")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = cfg["model"]

    conn = get_conn()
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(conn, alpha=m["alpha"])

    log.info("ALS 학습 중...")
    model = train(mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])

    # 유저 샘플링
    sample_user_ids = sample_users(mat, user_dec, n=args.users, min_history=args.min_history)
    log.info("검증 유저 %d명 선택 완료", len(sample_user_ids))

    # 시청 이력 로드
    history = load_watch_history(conn, sample_user_ids)

    # 추천 생성
    uid_indices = [user_enc[u] for u in sample_user_ids]
    item_indices, scores = model.recommend(
        uid_indices,
        mat[uid_indices],
        N=args.top_k,
        filter_already_liked_items=True,
    )

    # 모든 VOD ID 수집 후 제목 한번에 로드
    all_vod_ids = set()
    for u in sample_user_ids:
        all_vod_ids.update(v for v, _ in history.get(u, []))
    for row in item_indices:
        all_vod_ids.update(item_dec[i] for i in row)
    titles = load_vod_titles(conn, list(all_vod_ids))
    conn.close()

    # 출력
    print("\n" + "=" * 70)
    print("  CF_Engine 추천 결과 육안 검증")
    print("=" * 70)

    for idx, user_id in enumerate(sample_user_ids):
        print(f"\n[유저 {idx+1}] {user_id}")

        # 시청 이력
        user_history = history.get(user_id, [])
        print(f"\n  ▶ 시청 이력 (완료율 높은 순, 상위 10개)")
        for i, (vod_id, rate) in enumerate(user_history[:10], 1):
            title = titles.get(vod_id, "제목없음")
            print(f"     {i:2}. [{rate*100:5.1f}%] {title}")

        # 추천 결과
        print(f"\n  ★ CF 추천 결과 (Top-{args.top_k})")
        for rank, (iid, score) in enumerate(zip(item_indices[idx], scores[idx]), 1):
            vod_id = item_dec[iid]
            title = titles.get(vod_id, "제목없음")
            print(f"     {rank:2}. [score={score:.3f}] {title}")

        print("\n" + "-" * 70)


if __name__ == "__main__":
    main()
