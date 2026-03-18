"""
파일럿: 10명 유저별 추천 리스트 + 점수 + 급락 지점 시각화
- 유저별 추천 순위별 점수 막대 그래프 (의미있는 구간 vs 리스트 채우기 구간 색상 구분)
- 급락 지점 빨간 점선 표시
- 각 막대 위에 VOD 이름 출력
- 결과: docs/pilot_cutoff_visual_YYYYMMDD.png + docs/pilot_cutoff_visual_YYYYMMDD.md

실행: python scripts/pilot_cutoff_visual.py
      python scripts/pilot_cutoff_visual.py --users 10 --top-k 10
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
    if len(scores) < 2:
        return len(scores)
    drops = -np.diff(scores)
    mean_drop = drops.mean()
    for i, drop in enumerate(drops):
        if drop > mean_drop * (1 + threshold_ratio):
            return i + 1
    return len(scores)


def load_vod_names(conn) -> dict:
    cur = conn.cursor()
    cur.execute("SELECT full_asset_id, asset_nm FROM public.vod")
    result = {row[0]: row[1] for row in cur.fetchall()}
    cur.close()
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--users", type=int, default=10)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--min-history", type=int, default=5)
    parser.add_argument("--filter-quality", action="store_true", default=False)
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

    rng = np.random.default_rng(42)
    candidates = [uid for uid in range(mat.shape[0])
                  if mat.getrow(uid).nnz >= args.min_history]

    # 전체 후보에서 추천 점수를 먼저 뽑아 cutoff=1인 유저만 필터링
    log.info("cutoff=1 유저 탐색 중 (후보 %d명 중 스캔)...", len(candidates))
    scan_size = min(2000, len(candidates))
    scan_pool = rng.choice(candidates, size=scan_size, replace=False)
    scan_ids, scan_scores = model.recommend(
        scan_pool, mat[scan_pool],
        N=args.top_k, filter_already_liked_items=True,
    )
    cutoff1_indices = [
        scan_pool[i] for i, s in enumerate(scan_scores)
        if find_cutoff(s) == 1
    ]
    log.info("cutoff=1 유저: %d명 (%.1f%%)", len(cutoff1_indices),
             len(cutoff1_indices) / scan_size * 100)

    if not cutoff1_indices:
        log.error("cutoff=1 유저를 찾을 수 없습니다. 스캔 크기를 늘려보세요.")
        sys.exit(1)
    sampled = rng.choice(cutoff1_indices, size=min(args.users, len(cutoff1_indices)), replace=False)
    log.info("최종 샘플 %d명 (1위만 의미있는 유저)", len(sampled))

    ids_all, scores_all = model.recommend(
        sampled, mat[sampled],
        N=args.top_k, filter_already_liked_items=True,
    )

    # ── 유저별 데이터 수집 ────────────────────────────────────────
    users_data = []
    for uid_idx, user_scores, user_item_ids in zip(sampled, scores_all, ids_all):
        cutoff = find_cutoff(user_scores)
        real_uid = user_dec.get(int(uid_idx), str(uid_idx))

        recs = []
        for rank_i in range(len(user_scores)):
            vod_idx = int(user_item_ids[rank_i])
            vod_id = item_dec.get(vod_idx, "unknown")
            vod_name = vod_names.get(vod_id, vod_id[:10])
            recs.append({
                "rank": rank_i + 1,
                "vod_id": vod_id,
                "vod_name": vod_name,
                "score": float(user_scores[rank_i]),
                "meaningful": rank_i < cutoff,  # cutoff 이전이면 의미있는 추천
            })
        users_data.append({
            "user_id": real_uid,
            "cutoff": cutoff,
            "recs": recs,
            "history_count": int(mat.getrow(int(uid_idx)).nnz),
        })

    # ── 시각화 ────────────────────────────────────────────────────
    set_korean_font()
    n_users = len(users_data)
    cols = 2
    rows = (n_users + 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(cols * 12, rows * 5))
    axes = axes.flatten()

    filter_label = "필터 ON" if args.filter_quality else "필터 없음 (27.9% 혼합)"
    fig.suptitle(
        f"1위에서 급락하는 유저 샘플 {n_users}명 — {filter_label} | Top-{args.top_k}\n"
        f"(전체 유저 63%가 이 패턴: 1위만 의미있고 2위부터 리스트 채우기)",
        fontsize=13, fontweight="bold", y=1.02
    )

    for i, ud in enumerate(users_data):
        ax = axes[i]
        recs = ud["recs"]
        ranks = [r["rank"] for r in recs]
        scores = [r["score"] for r in recs]
        colors = ["#2ecc71" if r["meaningful"] else "#bdc3c7" for r in recs]
        vod_labels = [r["vod_name"][:12] + ("…" if len(r["vod_name"]) > 12 else "")
                      for r in recs]

        bars = ax.bar(ranks, scores, color=colors, edgecolor="white", linewidth=0.5)

        # 급락 지점 빨간 점선
        cutoff = ud["cutoff"]
        if cutoff < args.top_k:
            ax.axvline(x=cutoff + 0.5, color="red", linestyle="--", linewidth=2,
                       label=f"급락 지점 ({cutoff}위↓{cutoff+1}위)")

        # 막대 위에 점수 표시
        for bar, score in zip(bars, scores):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.005,
                    f"{score:.3f}", ha="center", va="bottom", fontsize=7, color="#2c3e50")

        # x축 VOD 이름
        ax.set_xticks(ranks)
        ax.set_xticklabels(vod_labels, rotation=35, ha="right", fontsize=7.5)

        uid_short = str(ud["user_id"])[:12] + "…"
        ax.set_title(
            f"유저 {uid_short}  |  이력 {ud['history_count']}개  |  의미있는 추천: {cutoff}위까지",
            fontsize=9, fontweight="bold"
        )
        ax.set_ylabel("ALS 추천 점수", fontsize=8)
        ax.set_ylim(0, max(scores) * 1.18 if max(scores) > 0 else 1.0)
        ax.legend(fontsize=8, loc="upper right")
        ax.grid(axis="y", alpha=0.3)

        # 범례 영역 색상 설명
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#2ecc71", label=f"의미있는 추천 (1~{cutoff}위)"),
            Patch(facecolor="#bdc3c7", label=f"리스트 채우기 ({cutoff+1}위~)"),
        ]
        ax.legend(handles=legend_elements, fontsize=7.5, loc="upper right")

    # 빈 subplot 숨기기
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    plt.tight_layout()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_img = Path("docs") / f"pilot_cutoff_visual_{timestamp}.png"
    out_img.parent.mkdir(exist_ok=True)
    plt.savefig(out_img, dpi=150, bbox_inches="tight")
    log.info("그래프 저장: %s", out_img)

    # ── 마크다운 리포트 ────────────────────────────────────────────
    report_path = Path("docs") / f"pilot_cutoff_visual_{timestamp}.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(f"# 파일럿: 유저별 추천 리스트 급락 지점 분석\n\n")
        f.write(f"- 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 샘플 유저: {n_users}명 | Top-K: {args.top_k} | 품질 필터: {'ON' if args.filter_quality else 'OFF (27.9% 혼합)'}\n\n")
        f.write(f"## 그래프\n\n")
        f.write(f"![유저별 추천 급락 지점]({out_img.name})\n\n")
        f.write(f"> 🟢 초록 막대: 의미있는 추천 (급락 이전) | ⬜ 회색 막대: 리스트 채우기 (급락 이후) | 빨간 점선: 급락 지점\n\n")
        f.write(f"---\n\n")

        f.write(f"## 유저별 결과 요약\n\n")
        f.write(f"| 유저 ID (앞 16자) | 시청 이력 | 의미있는 추천 수 | 급락 지점 점수 | 마지막 의미있는 VOD |\n")
        f.write(f"|-----------------|---------|--------------|-------------|-------------------|\n")
        for ud in users_data:
            cutoff = ud["cutoff"]
            cutoff_score = ud["recs"][cutoff - 1]["score"]
            last_vod = ud["recs"][cutoff - 1]["vod_name"]
            f.write(f"| {str(ud['user_id'])[:16]} | {ud['history_count']}개 | **{cutoff}개** | {cutoff_score:.4f} | {last_vod} |\n")

        f.write(f"\n---\n\n")
        f.write(f"## 유저별 전체 추천 리스트\n\n")

        for ud in users_data:
            cutoff = ud["cutoff"]
            f.write(f"### 유저 `{str(ud['user_id'])[:20]}…`\n\n")
            f.write(f"- 시청 이력: {ud['history_count']}개\n")
            f.write(f"- **의미있는 추천: 1~{cutoff}위** / 리스트 채우기: {cutoff+1}~{args.top_k}위\n\n")
            f.write(f"| 순위 | VOD 이름 | 점수 | 구분 |\n|------|---------|------|------|\n")
            for r in ud["recs"]:
                tag = "🟢 의미있는 추천" if r["meaningful"] else "⬜ 리스트 채우기"
                marker = " **◀ 급락**" if r["rank"] == cutoff else ""
                f.write(f"| {r['rank']}위 | {r['vod_name']} | {r['score']:.4f} | {tag}{marker} |\n")
            f.write("\n")

    log.info("리포트 저장: %s", report_path)
    print(f"\n✔ 그래프: {out_img}")
    print(f"✔ 리포트: {report_path}")


if __name__ == "__main__":
    main()
