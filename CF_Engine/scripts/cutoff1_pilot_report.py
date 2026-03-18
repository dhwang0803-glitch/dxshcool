"""
1위 급락 유저 대상 파일럿 테스트 + 추천 품질 점수화 보고서

- cutoff_rank == 1 유저 10명 샘플
- 시청 이력 vs 추천 결과 대조
- 추천 품질 점수: score_drop_ratio, genre_hit_rate, score_concentration

실행: python scripts/cutoff1_pilot_report.py
      python scripts/cutoff1_pilot_report.py --users 10 --top-k 10 --pool 2000
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

THRESHOLD_RATIO = 0.15  # find_cutoff 기준 (score_cutoff_analysis.py 동일)


def find_cutoff(scores: np.ndarray) -> int:
    if len(scores) < 2:
        return len(scores)
    drops = -np.diff(scores)
    mean_drop = drops.mean()
    for i, drop in enumerate(drops):
        if drop > mean_drop * (1 + THRESHOLD_RATIO):
            return i + 1
    return len(scores)


def load_vod_meta(conn, vod_ids: list) -> dict:
    """vod_id → {asset_nm, genre} 매핑"""
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(vod_ids))
    cur.execute(
        f"SELECT full_asset_id, asset_nm, genre FROM public.vod WHERE full_asset_id IN ({placeholders})",
        vod_ids,
    )
    result = {row[0]: {"asset_nm": row[1] or "(제목없음)", "genre": row[2] or "미분류"} for row in cur.fetchall()}
    cur.close()
    return result


def load_watch_history(conn, user_ids: list) -> dict:
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(user_ids))
    cur.execute(
        f"""
        SELECT user_id_fk, vod_id_fk, completion_rate
        FROM public.watch_history
        WHERE user_id_fk IN ({placeholders})
          AND completion_rate IS NOT NULL
        ORDER BY user_id_fk, completion_rate DESC
        """,
        user_ids,
    )
    history = {}
    for user_id, vod_id, rate in cur.fetchall():
        history.setdefault(user_id, []).append((vod_id, float(rate)))
    cur.close()
    return history


def compute_quality_scores(rec_scores: np.ndarray, rec_vod_ids: list,
                            history_vod_ids: list, vod_meta: dict) -> dict:
    """
    추천 품질 점수 3종
    - score_drop_ratio   : (1위점수 - 2위점수) / 1위점수  →  급락 강도 (높을수록 1위에 집중)
    - score_concentration: 1위 점수 / 전체 합              →  1위 쏠림 비율
    - genre_hit_rate     : 추천 VOD 중 시청 이력 장르와 겹치는 비율
    """
    s1 = float(rec_scores[0])
    s2 = float(rec_scores[1]) if len(rec_scores) > 1 else 0.0
    total = float(rec_scores.sum())

    score_drop_ratio = (s1 - s2) / s1 if s1 > 0 else 0.0
    score_concentration = s1 / total if total > 0 else 0.0

    # 시청 이력 장르 셋
    history_genres = {vod_meta[v]["genre"] for v in history_vod_ids if v in vod_meta}
    if history_genres:
        matched = sum(1 for v in rec_vod_ids if vod_meta.get(v, {}).get("genre") in history_genres)
        genre_hit_rate = matched / len(rec_vod_ids)
    else:
        genre_hit_rate = None

    return {
        "score_drop_ratio": score_drop_ratio,
        "score_concentration": score_concentration,
        "genre_hit_rate": genre_hit_rate,
    }


def grade_quality(genre_hit_rate, score_concentration) -> str:
    """종합 등급: 장르 적합도 + 점수 집중도 기반"""
    if genre_hit_rate is None:
        return "N/A"
    if genre_hit_rate >= 0.6 and score_concentration >= 0.15:
        return "★★★★★ 매우 좋음"
    if genre_hit_rate >= 0.4:
        return "★★★★☆ 좋음"
    if genre_hit_rate >= 0.2:
        return "★★★☆☆ 보통"
    return "★★☆☆☆ 미흡"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--users", type=int, default=10, help="파일럿 유저 수")
    parser.add_argument("--top-k", type=int, default=10, help="추천 Top-K")
    parser.add_argument("--pool", type=int, default=2000, help="cutoff 탐색 풀 크기")
    parser.add_argument("--min-history", type=int, default=5)
    args = parser.parse_args()

    with open(args.config, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    m = cfg["model"]

    conn = get_conn()
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(
        conn, alpha=m["alpha"], filter_quality=True
    )

    log.info("ALS 학습 중...")
    model = train(mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])

    # ── cutoff=1 유저 탐색 ─────────────────────────────────────────
    rng = np.random.default_rng(42)
    candidates = [uid for uid in range(mat.shape[0])
                  if mat.getrow(uid).nnz >= args.min_history]
    pool_idx = rng.choice(candidates, size=min(args.pool, len(candidates)), replace=False)

    pool_item_ids, pool_scores = model.recommend(
        pool_idx, mat[pool_idx], N=args.top_k, filter_already_liked_items=True
    )

    cutoff1_idx = [pool_idx[i] for i, s in enumerate(pool_scores)
                   if find_cutoff(s) == 1]
    log.info("풀 %d명 중 cutoff=1 유저: %d명 (%.1f%%)",
             len(pool_idx), len(cutoff1_idx), len(cutoff1_idx) / len(pool_idx) * 100)

    if len(cutoff1_idx) < args.users:
        log.warning("cutoff=1 유저가 %d명뿐입니다. 전원 사용.", len(cutoff1_idx))
        sampled_idx = np.array(cutoff1_idx)
    else:
        sampled_idx = rng.choice(cutoff1_idx, size=args.users, replace=False)

    # ── 추천 생성 ──────────────────────────────────────────────────
    rec_item_ids, rec_scores = model.recommend(
        sampled_idx, mat[sampled_idx], N=args.top_k, filter_already_liked_items=True
    )

    # ── 메타 로드 ──────────────────────────────────────────────────
    sample_user_ids = [user_dec[int(i)] for i in sampled_idx]
    history = load_watch_history(conn, sample_user_ids)

    all_vod_ids = set()
    for u in sample_user_ids:
        all_vod_ids.update(v for v, _ in history.get(u, []))
    for row in rec_item_ids:
        all_vod_ids.update(item_dec[int(i)] for i in row)
    vod_meta = load_vod_meta(conn, list(all_vod_ids))
    conn.close()

    # ── 결과 집계 ──────────────────────────────────────────────────
    results = []
    for idx, (uid_idx, user_id) in enumerate(zip(sampled_idx, sample_user_ids)):
        scores = rec_scores[idx]
        iids = rec_item_ids[idx]
        rec_vod_list = [item_dec[int(i)] for i in iids]
        history_vod_list = [v for v, _ in history.get(user_id, [])]

        quality = compute_quality_scores(scores, rec_vod_list, history_vod_list, vod_meta)
        grade = grade_quality(quality["genre_hit_rate"], quality["score_concentration"])

        results.append({
            "user_id": user_id,
            "history": history.get(user_id, [])[:10],
            "recommendations": [
                {
                    "rank": r + 1,
                    "vod_id": rec_vod_list[r],
                    "asset_nm": vod_meta.get(rec_vod_list[r], {}).get("asset_nm", "(없음)"),
                    "genre": vod_meta.get(rec_vod_list[r], {}).get("genre", "미분류"),
                    "score": float(scores[r]),
                }
                for r in range(len(scores))
            ],
            "quality": quality,
            "grade": grade,
            "history_genres": sorted({vod_meta.get(v, {}).get("genre", "미분류")
                                       for v, _ in history.get(user_id, [])[:10]}),
        })

    # ── 터미널 출력 ────────────────────────────────────────────────
    sep = "=" * 72
    print(f"\n{sep}")
    print("  1위 급락 유저 파일럿 테스트 — 추천 품질 점수화")
    print(sep)

    for r in results:
        print(f"\n▶ 유저: {r['user_id'][:20]}...")
        print(f"  시청 이력 장르: {', '.join(r['history_genres']) or '없음'}")
        print(f"  {'순위':>3} | {'점수':>7} | {'장르':>8} | VOD 제목")
        print(f"  {'-'*60}")
        for rec in r["recommendations"]:
            marker = " ◀ 급락" if rec["rank"] == 2 else ""
            print(f"  {rec['rank']:3}위 | {rec['score']:7.4f} | {rec['genre']:>8} | {rec['asset_nm'][:28]}{marker}")
        q = r["quality"]
        ghr = f"{q['genre_hit_rate']*100:.1f}%" if q["genre_hit_rate"] is not None else "N/A"
        print(f"\n  [품질 점수]  점수급락비율={q['score_drop_ratio']*100:.1f}%  "
              f"1위집중도={q['score_concentration']*100:.1f}%  "
              f"장르적합율={ghr}  →  {r['grade']}")

    # ── 마크다운 보고서 ────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path("docs") / f"cutoff1_pilot_report_{timestamp}.md"
    report_path.parent.mkdir(exist_ok=True)

    grade_counts = {}
    for r in results:
        grade_counts[r["grade"]] = grade_counts.get(r["grade"], 0) + 1

    avg_drop = np.mean([r["quality"]["score_drop_ratio"] for r in results]) * 100
    avg_conc = np.mean([r["quality"]["score_concentration"] for r in results]) * 100
    ghr_vals = [r["quality"]["genre_hit_rate"] for r in results if r["quality"]["genre_hit_rate"] is not None]
    avg_ghr = np.mean(ghr_vals) * 100 if ghr_vals else 0.0

    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# 1위 급락 유저 파일럿 테스트 — 추천 품질 점수화 보고서\n\n")
        f.write(f"- 일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"- 대상: cutoff_rank=1 유저 {len(results)}명 샘플 | Top-K: {args.top_k} | 품질 필터: ON\n")
        f.write(f"- 탐색 풀: {len(pool_idx)}명 중 cutoff=1 비율: {len(cutoff1_idx)/len(pool_idx)*100:.1f}%\n\n")

        f.write("---\n\n## 종합 품질 요약\n\n")
        f.write("| 지표 | 평균값 | 설명 |\n|------|--------|------|\n")
        f.write(f"| 점수 급락 비율 | {avg_drop:.1f}% | 1위→2위 점수 하락폭 / 1위 점수 |\n")
        f.write(f"| 1위 점수 집중도 | {avg_conc:.1f}% | 1위 점수 / Top-K 합계 |\n")
        f.write(f"| 장르 적합율 | {avg_ghr:.1f}% | 추천 중 시청이력 장르와 일치 비율 |\n\n")

        f.write("### 등급 분포\n\n")
        f.write("| 등급 | 유저 수 |\n|------|---------|\n")
        for grade, cnt in sorted(grade_counts.items(), reverse=True):
            f.write(f"| {grade} | {cnt}명 |\n")
        f.write("\n---\n\n")

        f.write("## 유저별 상세\n\n")
        for i, r in enumerate(results, 1):
            f.write(f"### 유저 {i} — {r['grade']}\n\n")
            f.write(f"- 유저 ID: `{r['user_id']}`\n")
            f.write(f"- 시청 이력 장르: {', '.join(r['history_genres']) or '없음'}\n\n")

            q = r["quality"]
            ghr_str = f"{q['genre_hit_rate']*100:.1f}%" if q["genre_hit_rate"] is not None else "N/A"
            f.write("**품질 점수**\n\n")
            f.write("| 지표 | 값 |\n|------|----|\n")
            f.write(f"| 점수 급락 비율 | {q['score_drop_ratio']*100:.1f}% |\n")
            f.write(f"| 1위 점수 집중도 | {q['score_concentration']*100:.1f}% |\n")
            f.write(f"| 장르 적합율 | {ghr_str} |\n\n")

            f.write("**시청 이력 (완료율 상위 10개)**\n\n")
            f.write("| 순서 | 완료율 | VOD 제목 | 장르 |\n|------|--------|----------|------|\n")
            for j, (vod_id, rate) in enumerate(r["history"], 1):
                meta = vod_meta.get(vod_id, {})
                f.write(f"| {j} | {rate*100:.1f}% | {meta.get('asset_nm', '(없음)')} | {meta.get('genre', '미분류')} |\n")

            f.write("\n**CF 추천 결과 Top-{}\n\n".format(args.top_k))
            f.write("| 순위 | 점수 | 장르 | VOD 제목 | 비고 |\n|------|------|------|----------|------|\n")
            for rec in r["recommendations"]:
                note = "◀ 급락 지점 (이후 리스트 채우기)" if rec["rank"] == 2 else ""
                f.write(f"| {rec['rank']}위 | {rec['score']:.4f} | {rec['genre']} | {rec['asset_nm']} | {note} |\n")
            f.write("\n")

        f.write("---\n\n## 인사이트\n\n")
        f.write("- cutoff=1 유저는 **1위 추천에 점수가 집중**되며, 2위부터 급격히 낮아짐.\n")
        f.write(f"- 평균 장르 적합율 {avg_ghr:.1f}%: 추천이 시청 이력 장르와 대체로 일치.\n")
        f.write("- 1위 이후 추천은 품질 저하 → **폴백 전략(인기 VOD 채우기)** 필요성 확인.\n")

    log.info("보고서 저장: %s", report_path)
    print(f"\n▶ 보고서 저장: {report_path}")


if __name__ == "__main__":
    main()
