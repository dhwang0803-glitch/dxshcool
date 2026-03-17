"""
유저별 추천 점수 급락 지점 분석
- 유저마다 "명확히 높은 점수 추천"과 "리스트 채우기" 경계를 찾음
- 급락 직전 VOD(마지막 의미있는 추천)가 어떤 콘텐츠인지 유저별로 출력
- 최적 K 결정 근거 제공
- 27.9% 저품질 VOD 폴백 전략 검토

실행: python scripts/score_cutoff_analysis.py
      python scripts/score_cutoff_analysis.py --users 500 --top-k 20
"""

import sys
import argparse
import logging
from datetime import datetime
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


def set_korean_font():
    candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic"]
    available = {f.name for f in fm.fontManager.ttflist}
    for font in candidates:
        if font in available:
            plt.rcParams["font.family"] = font
            break
    plt.rcParams["axes.unicode_minus"] = False


def find_cutoff(scores: np.ndarray, threshold_ratio: float = 0.15) -> int:
    """
    유저 1명의 점수 배열에서 급락 지점 탐지.
    전 순위 대비 하락폭이 평균 하락폭의 threshold_ratio 배 이상이면 급락.
    반환: 급락 직전 순위 (1-indexed). 없으면 전체 K 반환.
    """
    if len(scores) < 2:
        return len(scores)
    drops = -np.diff(scores)           # 양수 = 하락
    mean_drop = drops.mean()
    for i, drop in enumerate(drops):
        if drop > mean_drop * (1 + threshold_ratio):
            return i + 1              # 1-indexed 급락 직전 순위
    return len(scores)


def load_vod_names(conn) -> dict:
    """vod_id → asset_nm 딕셔너리 반환"""
    cur = conn.cursor()
    cur.execute("SELECT full_asset_id, asset_nm FROM public.vod")
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    log.info("VOD 이름 로드: %d건", len(result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--users", type=int, default=500)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--min-history", type=int, default=5)
    parser.add_argument("--filter-quality", action="store_true", default=False,
                        help="품질 필터 ON (poster_url + vod_embedding 있는 VOD만)")
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = cfg["model"]

    conn = get_conn()
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(
        conn, alpha=m["alpha"], filter_quality=args.filter_quality
    )
    vod_names = load_vod_names(conn)
    conn.close()

    log.info("ALS 학습 중...")
    model = train(mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])

    # 샘플링
    rng = np.random.default_rng(42)
    candidates = [uid for uid in range(mat.shape[0])
                  if mat.getrow(uid).nnz >= args.min_history]
    sampled = rng.choice(candidates, size=min(args.users, len(candidates)), replace=False)
    log.info("샘플 유저 %d명", len(sampled))

    ids_all, scores_all = model.recommend(
        sampled, mat[sampled],
        N=args.top_k, filter_already_liked_items=True,
    )

    # ── 유저별 급락 지점 분석 ──────────────────────────────────────
    cutoffs = []
    score_at_cutoff = []
    score_at_end = []

    # 유저별 상세 결과: (user_id, cutoff_rank, vod_id, vod_name, score)
    per_user_results = []

    for i, (uid_idx, user_scores, user_ids) in enumerate(zip(sampled, scores_all, ids_all)):
        cutoff = find_cutoff(user_scores)
        cutoffs.append(cutoff)
        score_at_cutoff.append(float(user_scores[cutoff - 1]))
        score_at_end.append(float(user_scores[-1]))

        # 급락 직전 VOD (마지막 의미있는 추천)
        vod_idx = int(user_ids[cutoff - 1])
        vod_id = item_dec.get(vod_idx, "unknown")
        vod_name = vod_names.get(vod_id, "(이름 없음)")
        real_user_id = user_dec.get(int(uid_idx), str(uid_idx))

        per_user_results.append({
            "user_id": real_user_id,
            "cutoff_rank": cutoff,
            "vod_id": vod_id,
            "vod_name": vod_name,
            "score": float(user_scores[cutoff - 1]),
            # 전체 추천 리스트 (순위, vod_id, vod_name, 점수)
            "recommendations": [
                {
                    "rank": r + 1,
                    "vod_id": item_dec.get(int(user_ids[r]), "unknown"),
                    "vod_name": vod_names.get(item_dec.get(int(user_ids[r]), ""), "(이름 없음)"),
                    "score": float(user_scores[r]),
                }
                for r in range(len(user_scores))
            ],
        })

    cutoffs = np.array(cutoffs)
    score_at_cutoff = np.array(score_at_cutoff)
    score_at_end = np.array(score_at_end)

    # ── 통계 ──────────────────────────────────────────────────────
    ranks = np.arange(1, args.top_k + 1)
    mean_scores = scores_all.mean(axis=0)

    cutoff_counts = np.bincount(cutoffs, minlength=args.top_k + 1)[1:]  # 1~top_k

    # 누적 비율
    cumsum = np.cumsum(cutoff_counts)
    cumrate = cumsum / len(cutoffs) * 100

    # ── 시각화 ────────────────────────────────────────────────────
    set_korean_font()
    fig, axes = plt.subplots(1, 3, figsize=(18, 5))
    fig.suptitle(f"유저별 추천 점수 급락 지점 분석 (유저 {len(sampled)}명, Top-{args.top_k})", fontsize=13)

    # 왼쪽: 급락 지점 분포 히스토그램
    ax = axes[0]
    ax.bar(ranks, cutoff_counts, color="steelblue", alpha=0.7)
    recommended_k = int(np.percentile(cutoffs, 50))  # 중앙값
    ax.axvline(x=recommended_k, color="red", linestyle="--", linewidth=2,
               label=f"중앙값 K={recommended_k}")
    ax.set_xlabel("급락 지점 순위")
    ax.set_ylabel("유저 수")
    ax.set_title("유저별 점수 급락 지점 분포")
    ax.set_xticks(ranks)
    ax.legend()
    ax.grid(axis="y", alpha=0.3)

    # 가운데: 누적 비율 (K 이내에 급락하는 유저 비율)
    ax2 = axes[1]
    ax2.plot(ranks, cumrate, marker="o", color="darkorange", linewidth=2)
    for pct in [50, 75, 90]:
        k_at_pct = np.searchsorted(cumrate, pct) + 1
        ax2.axhline(y=pct, color="gray", linestyle=":", alpha=0.7)
        ax2.axvline(x=k_at_pct, color="gray", linestyle=":", alpha=0.7)
        ax2.annotate(f"K={k_at_pct}\n({pct}%)", xy=(k_at_pct, pct),
                     fontsize=8, color="darkred")
    ax2.set_xlabel("K (순위)")
    ax2.set_ylabel("누적 유저 비율 (%)")
    ax2.set_title("K 이내 급락 유저 누적 비율")
    ax2.set_xticks(ranks)
    ax2.grid(alpha=0.3)

    # 오른쪽: 순위별 평균 점수 + 급락 분포 오버레이
    ax3 = axes[2]
    ax3.plot(ranks, mean_scores, marker="o", color="steelblue", linewidth=2, label="평균 점수")
    ax3_twin = ax3.twinx()
    ax3_twin.bar(ranks, cutoff_counts / len(cutoffs) * 100, alpha=0.3,
                 color="coral", label="급락 비율(%)")
    ax3.set_xlabel("추천 순위")
    ax3.set_ylabel("평균 점수", color="steelblue")
    ax3_twin.set_ylabel("급락 유저 비율 (%)", color="coral")
    ax3.set_title("순위별 평균 점수 vs 급락 분포")
    ax3.set_xticks(ranks)
    ax3.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out_img = Path("docs/score_cutoff_analysis.png")
    out_img.parent.mkdir(exist_ok=True)
    plt.savefig(out_img, dpi=150, bbox_inches="tight")
    log.info("그래프 저장: %s", out_img)

    # ── 집계 텍스트 요약 ────────────────────────────────────────────────
    k50 = int(np.searchsorted(cumrate, 50)) + 1
    k75 = int(np.searchsorted(cumrate, 75)) + 1
    k90 = int(np.searchsorted(cumrate, 90)) + 1

    print("\n" + "=" * 65)
    print("  유저별 추천 점수 급락 지점 분석")
    print("=" * 65)
    print(f"\n{'순위':>4} | {'급락 유저':>8} | {'누적 비율':>9} | 바")
    print("-" * 65)
    for rank in ranks:
        cnt = cutoff_counts[rank - 1]
        cr = cumrate[rank - 1]
        bar = "█" * int(cnt / cutoff_counts.max() * 25)
        marker = ""
        if rank == k50: marker = " ◀ 50% 유저"
        elif rank == k75: marker = " ◀ 75% 유저"
        elif rank == k90: marker = " ◀ 90% 유저"
        print(f"  {rank:2}위 | {cnt:6}명   | {cr:6.1f}%    | {bar}{marker}")

    print("=" * 65)
    print(f"\n▶ 급락 지점 중앙값:    {recommended_k}위")
    print(f"▶ 50% 유저 급락 기준:  K={k50} 이내")
    print(f"▶ 75% 유저 급락 기준:  K={k75} 이내")
    print(f"▶ 90% 유저 급락 기준:  K={k90} 이내")
    print(f"\n▶ 급락 지점 평균 점수: {score_at_cutoff.mean():.4f}")
    print(f"▶ Top-{args.top_k} 끝 평균 점수: {score_at_end.mean():.4f}")
    print(f"\n▶ 권장 K: {k75} (75% 유저의 의미있는 추천 커버)")

    # ── 유저별 상세 출력 ───────────────────────────────────────────
    print(f"\n{'─'*80}")
    print("  유저별 급락 지점 상세 (급락 직전 VOD = 마지막 의미있는 추천)")
    print(f"{'─'*80}")
    print(f"{'유저 ID':>20} | {'급락 순위':>6} | {'점수':>7} | 마지막 의미있는 추천 VOD")
    print("-" * 80)
    for r in per_user_results:
        vod_display = f"{r['vod_name'][:25]}" if r['vod_name'] != "(이름 없음)" else r['vod_id']
        print(f"  {str(r['user_id']):>18} | {r['cutoff_rank']:>4}위   | {r['score']:>7.4f} | {vod_display}")

    # 27.9% 폴백 전략 안내
    print(f"\n{'─'*65}")
    print("  27.9% 저품질 VOD 폴백 전략 제안")
    print(f"{'─'*65}")
    print(f"  K={k75} 이내: 필터된 고품질 VOD로 추천")
    print(f"  K={k75}~{args.top_k}: 저품질 VOD 중 시청 수 상위 항목으로 채우기")
    print(f"  → 추천 다양성 유지 + 과적합 방지")

    # ── 리포트 저장 ────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("docs") / f"score_cutoff_report_{timestamp}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 추천 점수 급락 지점 분석 리포트\n\n")
        f.write(f"- 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 샘플 유저: {len(sampled)}명 | Top-K: {args.top_k} | 품질 필터: {'ON' if args.filter_quality else 'OFF'}\n\n")

        f.write(f"## 급락 지점 분포\n\n")
        f.write(f"| 순위 | 급락 유저 수 | 누적 비율 |\n|------|------------|----------|\n")
        for rank in ranks:
            f.write(f"| {rank}위 | {cutoff_counts[rank-1]}명 | {cumrate[rank-1]:.1f}% |\n")

        f.write(f"\n## 핵심 지표\n\n")
        f.write(f"| 항목 | 값 |\n|------|----|\n")
        f.write(f"| 급락 지점 중앙값 | {recommended_k}위 |\n")
        f.write(f"| 50% 유저 커버 K | {k50} |\n")
        f.write(f"| 75% 유저 커버 K | {k75} |\n")
        f.write(f"| 90% 유저 커버 K | {k90} |\n")
        f.write(f"| 급락 지점 평균 점수 | {score_at_cutoff.mean():.4f} |\n")
        f.write(f"| Top-{args.top_k} 끝 평균 점수 | {score_at_end.mean():.4f} |\n")

        f.write(f"\n## 유저별 급락 지점 상세\n\n")
        f.write("> 급락 순위 = 마지막으로 의미있는 추천을 받은 순위. 이후는 리스트 채우기 구간.\n\n")
        f.write(f"| 유저 ID | 급락 순위 | 점수 | 마지막 의미있는 추천 VOD | VOD ID |\n")
        f.write(f"|---------|----------|------|------------------------|--------|\n")
        for r in per_user_results:
            vod_display = r['vod_name'] if r['vod_name'] != "(이름 없음)" else "-"
            f.write(f"| {r['user_id']} | {r['cutoff_rank']}위 | {r['score']:.4f} | {vod_display} | {r['vod_id']} |\n")

        f.write(f"\n## 유저별 전체 추천 리스트 (급락 지점 표시)\n\n")
        for r in per_user_results:
            f.write(f"### 유저 {r['user_id']} — 급락: {r['cutoff_rank']}위\n\n")
            f.write(f"| 순위 | VOD 이름 | 점수 | 비고 |\n|------|---------|------|------|\n")
            for rec in r['recommendations']:
                note = "◀ 급락 지점 (이후 리스트 채우기)" if rec['rank'] == r['cutoff_rank'] else ""
                f.write(f"| {rec['rank']}위 | {rec['vod_name']} | {rec['score']:.4f} | {note} |\n")
            f.write("\n")

        f.write(f"\n## 권장 K 및 폴백 전략\n\n")
        f.write(f"- **권장 K: {k75}** (75% 유저의 의미있는 추천 커버)\n")
        f.write(f"- K={k75} 이내: 필터된 고품질 VOD (poster+embedding 있는 VOD) 추천\n")
        f.write(f"- K={k75}~{args.top_k}: 저품질 VOD 중 전체 시청 수 상위 항목으로 폴백\n")
        f.write(f"\n![그래프](score_cutoff_analysis.png)\n")

    log.info("리포트 저장: %s", report_path)


if __name__ == "__main__":
    main()
