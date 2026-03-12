"""
추천 품질 평가 (Hold-out 방식)

실행: python scripts/evaluate.py
      python scripts/evaluate.py --config config/als_config.yaml --k 20
"""

import sys
import time
import logging
import argparse
from pathlib import Path
from datetime import datetime

import yaml
import numpy as np
from scipy.sparse import csr_matrix

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


def split_holdout(mat: csr_matrix):
    """유저별 마지막(최대 인덱스) 아이템 1건을 테스트셋으로 분리."""
    train_data = mat.copy().tolil()
    test_items = {}

    for uid in range(mat.shape[0]):
        row = mat.getrow(uid)
        nz = row.nonzero()[1]
        if len(nz) < 2:
            continue
        hold = int(nz[-1])
        test_items[uid] = hold
        train_data[uid, hold] = 0

    return csr_matrix(train_data), test_items


def ndcg_at_k(recommended: list, relevant: int, k: int) -> float:
    dcg = sum(1.0 / np.log2(i + 2) for i, item in enumerate(recommended[:k]) if item == relevant)
    idcg = 1.0 / np.log2(2)
    return dcg / idcg


def evaluate(model, train_mat: csr_matrix, test_items: dict, k: int):
    ndcg_scores, mrr_scores, hits = [], [], []

    user_list = list(test_items.keys())
    item_indices, _ = model.recommend(
        user_list,
        train_mat[user_list],
        N=k,
        filter_already_liked_items=True,
    )

    for i, uid in enumerate(user_list):
        relevant = test_items[uid]
        recs = item_indices[i].tolist()

        hit = int(relevant in recs)
        hits.append(hit)
        ndcg_scores.append(ndcg_at_k(recs, relevant, k))
        rank = recs.index(relevant) + 1 if relevant in recs else None
        mrr_scores.append(1.0 / rank if rank else 0.0)

    return {
        f"NDCG@{k}": np.mean(ndcg_scores),
        f"MRR": np.mean(mrr_scores),
        f"HitRate@{k}": np.mean(hits),
        "eval_users": len(user_list),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--k", type=int, default=20)
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = cfg["model"]

    t0 = time.time()
    conn = get_conn()
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(conn, alpha=m["alpha"])
    conn.close()

    log.info("Hold-out 분리 중...")
    train_mat, test_items = split_holdout(mat)
    log.info("테스트 유저: %d명", len(test_items))

    model = train(train_mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])

    log.info("평가 중 (k=%d)...", args.k)
    metrics = evaluate(model, train_mat, test_items, k=args.k)

    log.info("=" * 45)
    for key, val in metrics.items():
        log.info("  %-15s %.4f" if isinstance(val, float) else "  %-15s %d", key, val)
    log.info("  소요: %.1f초", time.time() - t0)
    log.info("=" * 45)

    # 리포트 저장
    report_dir = Path("docs")
    report_dir.mkdir(exist_ok=True)
    date_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"eval_report_{date_str}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# CF_Engine 평가 리포트 — {date_str}\n\n")
        f.write(f"| 지표 | 값 |\n|------|----|\n")
        for key, val in metrics.items():
            f.write(f"| {key} | {val:.4f if isinstance(val, float) else val} |\n")
        f.write(f"\n- 모델: ALS factors={m['factors']}, iterations={m['iterations']}\n")
        f.write(f"- k={args.k}\n")
    log.info("리포트 저장: %s", report_path)


if __name__ == "__main__":
    main()
