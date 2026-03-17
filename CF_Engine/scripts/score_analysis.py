"""
추천 점수 분포 분석 — 순위별 점수 시각화
- 어느 순위부터 점수가 급락하는지 (= 그냥 채운 구간) 확인
- 유저별 점수 막대 + 순위별 평균 점수 꺾은선 출력

실행: python scripts/score_analysis.py
      python scripts/score_analysis.py --users 100 --top-k 20
"""

import sys
import argparse
import logging
from pathlib import Path

import yaml
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

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

# 한글 폰트 설정
def _set_korean_font():
    candidates = [
        "Malgun Gothic", "NanumGothic", "AppleGothic", "NanumBarunGothic"
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in candidates:
        if font in available:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False


def sample_users(mat, user_decoder, n, min_history=5, seed=42):
    rng = np.random.default_rng(seed)
    candidates = [uid for uid in range(mat.shape[0]) if mat.getrow(uid).nnz >= min_history]
    sampled = rng.choice(candidates, size=min(n, len(candidates)), replace=False)
    return [user_decoder[uid] for uid in sampled], list(sampled)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--min-history", type=int, default=5)
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = cfg["model"]

    conn = get_conn()
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(conn, alpha=m["alpha"])
    conn.close()

    log.info("ALS 학습 중...")
    model = train(mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])

    user_ids, uid_indices = sample_users(mat, user_dec, n=args.users, min_history=args.min_history)
    log.info("샘플 유저 %d명", len(uid_indices))

    _, scores_all = model.recommend(
        uid_indices,
        mat[uid_indices],
        N=args.top_k,
        filter_already_liked_items=True,
    )
    # scores_all: (n_users, top_k)

    _set_korean_font()

    # ── 그래프 1: 순위별 평균 점수 + 표준편차 ──────────────────────────
    ranks = np.arange(1, args.top_k + 1)
    mean_scores = scores_all.mean(axis=0)
    std_scores  = scores_all.std(axis=0)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    fig.suptitle(f"CF_Engine 추천 점수 분포 분석 (유저 {len(uid_indices)}명, Top-{args.top_k})", fontsize=13)

    # 왼쪽: 순위별 평균 점수
    ax = axes[0]
    ax.plot(ranks, mean_scores, marker="o", color="steelblue", linewidth=2, label="평균 점수")
    ax.fill_between(ranks, mean_scores - std_scores, mean_scores + std_scores,
                    alpha=0.2, color="steelblue", label="±1 표준편차")

    # 점수 급락 구간 탐지 (전 순위 대비 하락폭이 가장 큰 지점)
    drops = np.diff(mean_scores)           # 음수 = 하락
    cliff_rank = int(np.argmin(drops)) + 1 # 1-indexed, 가장 많이 하락한 직전 순위
    ax.axvline(x=cliff_rank + 0.5, color="red", linestyle="--", linewidth=1.5,
               label=f"점수 급락 구간 (순위 {cliff_rank}→{cliff_rank+1})")

    ax.set_xlabel("추천 순위")
    ax.set_ylabel("ALS 추천 점수")
    ax.set_title("순위별 평균 점수")
    ax.set_xticks(ranks)
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)

    # 오른쪽: 유저별 점수 히트맵 (상위 30명만)
    ax2 = axes[1]
    sample_n = min(30, len(scores_all))
    im = ax2.imshow(scores_all[:sample_n], aspect="auto", cmap="YlOrRd",
                    vmin=0, vmax=scores_all.max())
    ax2.axvline(x=cliff_rank - 0.5, color="red", linestyle="--", linewidth=1.5,
                label=f"급락 기준선 (순위 {cliff_rank})")
    ax2.set_xlabel("추천 순위")
    ax2.set_ylabel("유저 (샘플 30명)")
    ax2.set_title("유저별 점수 히트맵")
    ax2.set_xticks(range(args.top_k))
    ax2.set_xticklabels(ranks, fontsize=8)
    plt.colorbar(im, ax=ax2, label="점수")
    ax2.legend(fontsize=8)

    plt.tight_layout()
    out_path = Path("docs/score_analysis.png")
    out_path.parent.mkdir(exist_ok=True)
    plt.savefig(out_path, dpi=150, bbox_inches="tight")
    log.info("그래프 저장: %s", out_path)

    # ── 텍스트 요약 ────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  순위별 평균 점수 요약")
    print("=" * 60)
    print(f"{'순위':>4} | {'평균 점수':>9} | {'표준편차':>8} | 바")
    print("-" * 60)
    bar_max = 30
    for i, (rank, mean, std) in enumerate(zip(ranks, mean_scores, std_scores)):
        bar_len = int(mean / mean_scores[0] * bar_max)
        bar = "█" * bar_len
        marker = " ◀ 급락" if i == cliff_rank - 1 else ""
        print(f"  {rank:2}위 | {mean:9.4f} | {std:8.4f} | {bar}{marker}")
    print("=" * 60)
    print(f"\n▶ 점수 급락 구간: 순위 {cliff_rank} → {cliff_rank+1} (하락폭 {abs(drops[cliff_rank-1]):.4f})")
    print(f"▶ 순위 1 평균 점수:  {mean_scores[0]:.4f}")
    print(f"▶ 순위 {args.top_k} 평균 점수: {mean_scores[-1]:.4f}")
    print(f"▶ 전체 하락률: {(1 - mean_scores[-1]/mean_scores[0])*100:.1f}%")
    print(f"\n그래프 → {out_path.resolve()}")


if __name__ == "__main__":
    main()
