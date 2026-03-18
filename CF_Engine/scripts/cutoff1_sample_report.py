"""
1위 급락 유저 샘플 리포트
- 전체 유저 중 급락 지점이 1위인 유저(64.8%)에서 10명을 뽑아
  추천 리스트(VOD 이름 + 점수)를 마크다운 리포트로 저장한다.

실행: python scripts/cutoff1_sample_report.py
      python scripts/cutoff1_sample_report.py --users 500 --top-k 20 --sample 10
"""

import sys
import argparse
import logging
from datetime import datetime
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
    log.info("VOD 이름 로드: %d건", len(result))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--users", type=int, default=500,
                        help="분석 대상 유저 수 (급락 지점 탐색용 풀)")
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--min-history", type=int, default=5)
    parser.add_argument("--sample", type=int, default=10,
                        help="리포트에 포함할 1위 급락 유저 수")
    parser.add_argument("--filter-quality", action="store_true", default=True,
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

    rng = np.random.default_rng(42)
    candidates = [uid for uid in range(mat.shape[0])
                  if mat.getrow(uid).nnz >= args.min_history]
    sampled = rng.choice(candidates, size=min(args.users, len(candidates)), replace=False)
    log.info("샘플 유저 %d명", len(sampled))

    ids_all, scores_all = model.recommend(
        sampled, mat[sampled],
        N=args.top_k, filter_already_liked_items=True,
    )

    # 급락 지점 1위인 유저만 추출
    cutoff1_users = []
    for uid_idx, user_scores, user_ids in zip(sampled, scores_all, ids_all):
        cutoff = find_cutoff(user_scores)
        if cutoff != 1:
            continue
        real_user_id = user_dec.get(int(uid_idx), str(uid_idx))
        recommendations = [
            {
                "rank": r + 1,
                "vod_id": item_dec.get(int(user_ids[r]), "unknown"),
                "vod_name": vod_names.get(item_dec.get(int(user_ids[r]), ""), "(이름 없음)"),
                "score": float(user_scores[r]),
            }
            for r in range(len(user_scores))
        ]
        cutoff1_users.append({
            "user_id": real_user_id,
            "history_count": mat.getrow(int(uid_idx)).nnz,
            "score_1st": float(user_scores[0]),
            "score_2nd": float(user_scores[1]),
            "score_drop": float(user_scores[0] - user_scores[1]),
            "recommendations": recommendations,
        })

    log.info("1위 급락 유저: %d명 / %d명 (%.1f%%)",
             len(cutoff1_users), len(sampled),
             len(cutoff1_users) / len(sampled) * 100)

    # 10명 선택 (급락 폭 큰 순)
    cutoff1_users.sort(key=lambda x: x["score_drop"], reverse=True)
    selected = cutoff1_users[:args.sample]

    # 리포트 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("docs") / f"cutoff1_sample_report_{timestamp}.md"

    lines = []
    lines.append("# 1위 급락 유저 샘플 리포트\n")
    lines.append(f"- **일시**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **분석 풀**: {len(sampled)}명 (시청 이력 {args.min_history}개 이상)")
    lines.append(f"- **1위 급락 유저**: {len(cutoff1_users)}명 "
                 f"({len(cutoff1_users)/len(sampled)*100:.1f}%)")
    lines.append(f"- **선택 기준**: 급락 폭(1위→2위 점수 차) 상위 {args.sample}명")
    lines.append(f"- **Top-K**: {args.top_k} | 품질 필터: {'ON' if args.filter_quality else 'OFF'}")
    lines.append(f"- **모델**: ALS (factors={m['factors']}, iterations={m['iterations']}, "
                 f"regularization={m['regularization']}, alpha={m['alpha']})\n")
    lines.append("---\n")

    lines.append("## 요약\n")
    lines.append("| # | 유저 ID | 시청 이력 | 1위 점수 | 2위 점수 | 급락 폭 |")
    lines.append("|---|---------|---------|---------|---------|--------|")
    for i, u in enumerate(selected, 1):
        lines.append(f"| {i} | `{u['user_id']}` | {u['history_count']}개 | "
                     f"{u['score_1st']:.4f} | {u['score_2nd']:.4f} | "
                     f"**{u['score_drop']:.4f}** |")

    lines.append("\n---\n")
    lines.append("## 유저별 추천 리스트\n")

    for i, u in enumerate(selected, 1):
        lines.append(f"### {i}. 유저 `{u['user_id']}`")
        lines.append(f"- 시청 이력: {u['history_count']}개")
        lines.append(f"- 1위→2위 급락 폭: **{u['score_drop']:.4f}** "
                     f"({u['score_1st']:.4f} → {u['score_2nd']:.4f})\n")
        lines.append("| 순위 | VOD 이름 | 점수 | 비고 |")
        lines.append("|------|---------|------|------|")
        for rec in u["recommendations"]:
            note = "◀ **1위 이후 급락**" if rec["rank"] == 2 else ""
            lines.append(f"| {rec['rank']}위 | {rec['vod_name']} | "
                         f"{rec['score']:.4f} | {note} |")
        lines.append("")

    report_path.parent.mkdir(exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info("리포트 저장: %s", report_path)
    print(f"\n✓ 리포트: {report_path}")


if __name__ == "__main__":
    main()
