"""
CF_Engine 종합 추천 적절성 평가
- NDCG@K, MRR, HitRate@K, Precision@K, Coverage
- 필터 전/후 비교
- 유저 이력 수 세그먼트별 분석 (Cold / Warm / Hot)

실행: python scripts/full_eval.py
      python scripts/full_eval.py --k 10
"""

import sys
import time
import argparse
import logging
from datetime import datetime
from pathlib import Path

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


# ── 지표 계산 함수 ─────────────────────────────────────────────────

def split_holdout(mat: csr_matrix):
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


def ndcg_at_k(recommended, relevant, k):
    dcg = sum(1.0 / np.log2(i + 2) for i, item in enumerate(recommended[:k]) if item == relevant)
    return dcg / (1.0 / np.log2(2))


def run_eval(model, train_mat, test_items, k, mat_original):
    """전체 지표 계산 + 세그먼트별 분석"""
    user_list = list(test_items.keys())
    item_indices_all, _ = model.recommend(
        user_list, train_mat[user_list],
        N=k, filter_already_liked_items=True,
    )

    ndcg_scores, mrr_scores, hits, precisions = [], [], [], []
    recommended_items = set()

    # 세그먼트: 유저 이력 수 기준
    seg_results = {"cold (2~4)": [], "warm (5~19)": [], "hot (20+)": []}

    for i, uid in enumerate(user_list):
        relevant = test_items[uid]
        recs = item_indices_all[i].tolist()
        recommended_items.update(recs)

        hit = int(relevant in recs)
        ndcg = ndcg_at_k(recs, relevant, k)
        rank = recs.index(relevant) + 1 if relevant in recs else None
        mrr = 1.0 / rank if rank else 0.0
        precision = hit / k

        hits.append(hit)
        ndcg_scores.append(ndcg)
        mrr_scores.append(mrr)
        precisions.append(precision)

        # 세그먼트 분류
        history_cnt = mat_original.getrow(uid).nnz
        if history_cnt < 5:
            seg_results["cold (2~4)"].append((ndcg, mrr, hit))
        elif history_cnt < 20:
            seg_results["warm (5~19)"].append((ndcg, mrr, hit))
        else:
            seg_results["hot (20+)"].append((ndcg, mrr, hit))

    n_items = train_mat.shape[1]
    coverage = len(recommended_items) / n_items if n_items > 0 else 0

    metrics = {
        f"NDCG@{k}":      np.mean(ndcg_scores),
        f"MRR":            np.mean(mrr_scores),
        f"HitRate@{k}":   np.mean(hits),
        f"Precision@{k}": np.mean(precisions),
        "Coverage":        coverage,
        "eval_users":      len(user_list),
        "n_items":         n_items,
    }
    return metrics, seg_results


def seg_summary(seg_results):
    rows = {}
    for seg, data in seg_results.items():
        if not data:
            rows[seg] = (0, 0.0, 0.0, 0.0)
            continue
        arr = np.array(data)
        rows[seg] = (len(data), arr[:, 0].mean(), arr[:, 1].mean(), arr[:, 2].mean())
    return rows


# ── 메인 ──────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--k", type=int, default=10)
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m_cfg = cfg["model"]

    results = {}
    seg_results_all = {}

    for label, use_filter in [("기존 (필터 없음)", False), ("필터 적용 (poster+embedding)", True)]:
        log.info("=" * 55)
        log.info("[%s] 평가 시작", label)
        t0 = time.time()

        conn = get_conn()
        mat, _, _, _, _ = load_matrix(conn, alpha=m_cfg["alpha"], filter_quality=use_filter)
        conn.close()

        train_mat, test_items = split_holdout(mat)
        log.info("테스트 유저: %d명", len(test_items))

        model = train(train_mat, factors=m_cfg["factors"],
                      iterations=m_cfg["iterations"],
                      regularization=m_cfg["regularization"])

        metrics, seg = run_eval(model, train_mat, test_items, args.k, mat)
        metrics["elapsed"] = time.time() - t0
        results[label] = metrics
        seg_results_all[label] = seg_summary(seg)

        for key, val in metrics.items():
            if isinstance(val, float):
                log.info("  %-20s %.4f", key, val)
            else:
                log.info("  %-20s %s", key, val)

    # ── 리포트 생성 ────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("docs") / f"full_eval_report_{timestamp}.md"
    report_path.parent.mkdir(exist_ok=True)

    labels = list(results.keys())
    k = args.k

    lines = []
    lines.append(f"# CF_Engine 종합 추천 적절성 평가 리포트\n\n")
    lines.append(f"- 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
    lines.append(f"- 모델: ALS (factors={m_cfg['factors']}, iterations={m_cfg['iterations']}, regularization={m_cfg['regularization']})\n")
    lines.append(f"- k={k}\n\n")

    # 지표 설명
    lines.append("## 지표 설명\n\n")
    lines.append("| 지표 | 의미 | 기준 |\n|------|------|------|\n")
    lines.append(f"| NDCG@{k} | 추천 순위의 질 — 정답이 상위에 있을수록 높음 | 0.3 이상이면 좋음 |\n")
    lines.append(f"| MRR | 정답이 처음 등장하는 순위의 역수 평균 | 0.2 이상이면 좋음 |\n")
    lines.append(f"| HitRate@{k} | Top-{k} 안에 정답이 1개라도 있는 유저 비율 | 0.6 이상이면 좋음 |\n")
    lines.append(f"| Precision@{k} | 추천 {k}개 중 정답 비율 | HitRate/{k} |\n")
    lines.append(f"| Coverage | 전체 아이템 중 추천에 등장하는 비율 (다양성) | 높을수록 다양 |\n\n")

    # 전체 비교표
    lines.append("## 필터 전/후 전체 성능 비교\n\n")
    lines.append(f"| 지표 | {labels[0]} | {labels[1]} | 변화 |\n")
    lines.append("|------|------------|------------|------|\n")

    metric_keys = [f"NDCG@{k}", "MRR", f"HitRate@{k}", f"Precision@{k}", "Coverage"]
    for key in metric_keys:
        v0 = results[labels[0]][key]
        v1 = results[labels[1]][key]
        diff = v1 - v0
        arrow = "↑" if diff > 0 else "↓"
        lines.append(f"| {key} | {v0:.4f} | {v1:.4f} | {diff:+.4f} {arrow} |\n")

    for label in labels:
        lines.append(f"\n> **{label}**: 평가 유저 {results[label]['eval_users']:,}명 / 아이템 {results[label]['n_items']:,}개 / 소요 {results[label]['elapsed']:.1f}초\n")

    # 세그먼트별 분석
    lines.append("\n## 유저 이력 수 세그먼트별 성능\n\n")
    for label in labels:
        lines.append(f"### {label}\n\n")
        lines.append(f"| 세그먼트 | 유저 수 | NDCG@{k} | MRR | HitRate@{k} |\n")
        lines.append("|----------|---------|----------|-----|------------|\n")
        for seg, (cnt, ndcg, mrr, hit) in seg_results_all[label].items():
            lines.append(f"| {seg} | {cnt:,}명 | {ndcg:.4f} | {mrr:.4f} | {hit:.4f} |\n")
        lines.append("\n")

    # 종합 해석
    lines.append("## 종합 해석\n\n")
    base = results[labels[0]]
    filt = results[labels[1]]

    def safe_pct(a, b):
        return (a - b) / b * 100 if b > 0 else 0.0

    ndcg_imp = safe_pct(filt[f'NDCG@{k}'], base[f'NDCG@{k}'])
    hit_imp  = safe_pct(filt[f'HitRate@{k}'], base[f'HitRate@{k}'])
    mrr_imp  = safe_pct(filt['MRR'], base['MRR'])

    lines.append(f"- poster_url 또는 vod_embedding 없는 VOD 제거 시 NDCG {ndcg_imp:+.1f}%, HitRate {hit_imp:+.1f}%, MRR {mrr_imp:+.1f}% 향상\n")

    # Cold/Warm/Hot 해석
    for label in labels:
        segs = seg_results_all[label]
        cold_hit = segs.get("cold (2~4)", (0,0,0,0))[3]
        hot_hit  = segs.get("hot (20+)",  (0,0,0,0))[3]
        lines.append(f"- [{label}] Cold(이력 2~4개) HitRate: {cold_hit:.4f} / Hot(20개+) HitRate: {hot_hit:.4f}\n")

    lines.append(f"\n> 기준: NDCG@{k} 0.3 이상 = 매우 좋음 / HitRate@{k} 0.6 이상 = 매우 좋음\n")

    with open(report_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    log.info("리포트 저장: %s", report_path.resolve())
    print(f"\n▶ 리포트: {report_path.resolve()}")


if __name__ == "__main__":
    main()
