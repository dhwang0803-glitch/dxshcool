"""Hybrid(CF+VS) 시리즈 확장 평가 스크립트.

기존 evaluate_recommendation.py와 동일한 Temporal Split 방식이되,
시리즈 대표 VOD → 에피소드 확장 매칭을 지원한다.

평가 모드:
  --mode strict   : 기존 방식 (VOD ID 정확 매칭만)
  --mode expanded : 시리즈 확장 매칭 (대표 VOD → 같은 시리즈 에피소드도 hit)

Usage:
    python Hybrid_Layer/scripts/evaluate_hybrid_vs.py
    python Hybrid_Layer/scripts/evaluate_hybrid_vs.py --mode expanded --top-k 10
"""
import argparse
import math
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DEFAULT_PARQUET = str(
    Path(__file__).parent.parent.parent / "Database_Design" / "data" / "202302_watch_history.parquet"
)
EXCLUDE_RAG_SOURCES = frozenset(["TMDB_NEW_2025"])


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_user_watch_counts(conn) -> dict[str, int]:
    """유저별 시청 횟수 로드 (watch_history 기준)."""
    cur = conn.cursor()
    cur.execute("SELECT user_id_fk, COUNT(*) FROM public.watch_history GROUP BY user_id_fk")
    result = {uid: cnt for uid, cnt in cur.fetchall()}
    cur.close()
    return result


def load_exclude_vods(conn) -> set[str]:
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(EXCLUDE_RAG_SOURCES))
    cur.execute(
        f"SELECT full_asset_id FROM public.vod WHERE rag_source IN ({placeholders})",
        tuple(EXCLUDE_RAG_SOURCES),
    )
    exclude = {row[0] for row in cur.fetchall()}
    cur.close()
    print(f"[필터] 평가 제외 VOD: {len(exclude):,}건")
    return exclude


def load_series_episode_map(conn) -> dict[str, set[str]]:
    """시리즈 대표 VOD → 같은 시리즈 전체 에피소드 매핑.

    Returns: {representative_vod_id: {ep1, ep2, ...}} (대표 자기 자신 포함)
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT se.representative_vod_id, v.full_asset_id
        FROM public.vod_series_embedding se
        JOIN public.vod v ON v.series_nm = se.series_nm
    """)
    mapping: dict[str, set[str]] = {}
    for rep_id, ep_id in cur.fetchall():
        mapping.setdefault(rep_id, set()).add(ep_id)
    cur.close()
    print(f"[시리즈 맵] 대표 VOD {len(mapping):,}건 → 에피소드 확장")
    return mapping


def load_feb_ground_truth(parquet_path: str) -> dict[str, set[str]]:
    df = pd.read_parquet(parquet_path, columns=["user_id_fk", "vod_id_fk"])
    gt: dict[str, set[str]] = {}
    for uid, vid in zip(df["user_id_fk"], df["vod_id_fk"]):
        gt.setdefault(uid, set()).add(vid)
    return gt


def load_recommendations(conn, rec_type: str, exclude_vods: set[str]) -> dict[str, list[str]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id_fk, vod_id_fk, rank
        FROM serving.vod_recommendation
        WHERE recommendation_type = %s AND user_id_fk IS NOT NULL
        ORDER BY user_id_fk, rank
    """, (rec_type,))
    recs: dict[str, list[str]] = {}
    for uid, vid, rank in cur.fetchall():
        if vid not in exclude_vods:
            recs.setdefault(uid, []).append(vid)
    cur.close()
    return recs


def load_hybrid_recommendations(conn, exclude_vods: set[str]) -> dict[str, list[str]]:
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id_fk, vod_id_fk, rank
        FROM serving.hybrid_recommendation
        ORDER BY user_id_fk, rank
    """)
    recs: dict[str, list[str]] = {}
    for uid, vid, rank in cur.fetchall():
        if vid not in exclude_vods:
            recs.setdefault(uid, []).append(vid)
    cur.close()
    return recs


# ── 평가 함수 ──────────────────────────────────────────────────

def expand_vod(vod_id: str, series_map: dict[str, set[str]] | None) -> set[str]:
    """VOD ID를 시리즈 에피소드로 확장. 매핑 없으면 자기 자신만."""
    if series_map is None:
        return {vod_id}
    return series_map.get(vod_id, {vod_id})


def dcg_at_k(ranked_list: list[str], relevant: set[str], k: int,
             series_map: dict[str, set[str]] | None = None) -> float:
    dcg = 0.0
    for i, item in enumerate(ranked_list[:k]):
        expanded = expand_vod(item, series_map)
        if expanded & relevant:
            dcg += 1.0 / math.log2(i + 2)
    return dcg


def ndcg_at_k(ranked_list: list[str], relevant: set[str], k: int,
              series_map: dict[str, set[str]] | None = None) -> float:
    dcg = dcg_at_k(ranked_list, relevant, k, series_map)
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    return dcg / idcg if idcg > 0 else 0.0


def evaluate(
    recs: dict[str, list[str]],
    ground_truth: dict[str, set[str]],
    top_k: int,
    series_map: dict[str, set[str]] | None = None,
    user_filter: set[str] | None = None,
) -> dict:
    eval_users = set(recs.keys()) & set(ground_truth.keys())
    if user_filter is not None:
        eval_users &= user_filter
    if not eval_users:
        return {"error": "평가 대상 유저 없음"}

    hits = 0
    total_precision = 0.0
    total_recall = 0.0
    total_ndcg = 0.0
    total_matched = 0

    for uid in eval_users:
        rec_list = recs[uid][:top_k]
        actual = ground_truth[uid]

        # 시리즈 확장 매칭
        matched_count = 0
        for vid in rec_list:
            expanded = expand_vod(vid, series_map)
            if expanded & actual:
                matched_count += 1

        if matched_count > 0:
            hits += 1

        precision = matched_count / len(rec_list) if rec_list else 0.0
        recall = matched_count / len(actual) if actual else 0.0
        ndcg = ndcg_at_k(rec_list, actual, top_k, series_map)

        total_precision += precision
        total_recall += recall
        total_ndcg += ndcg
        total_matched += matched_count

    n = len(eval_users)
    return {
        "eval_users": n,
        "hit_rate": round(hits / n, 4),
        "precision@k": round(total_precision / n, 4),
        "recall@k": round(total_recall / n, 4),
        "ndcg@k": round(total_ndcg / n, 4),
        "avg_matched": round(total_matched / n, 2),
    }


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="Hybrid(CF+VS) 시리즈 확장 평가")
    parser.add_argument("--parquet", default=DEFAULT_PARQUET)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--mode", choices=["strict", "expanded"], default="expanded",
                        help="strict=기존 정확 매칭, expanded=시리즈 확장 매칭")
    parser.add_argument("--segment", action="store_true",
                        help="콜드스타트/웜/헤비 유저 세그먼트별 평가 추가")
    args = parser.parse_args()

    if not os.path.exists(args.parquet):
        print(f"[ERROR] parquet 없음: {args.parquet}")
        sys.exit(1)

    print("=" * 65)
    print(f"Hybrid(CF+VS) 평가 -- mode={args.mode}, top_k={args.top_k}")
    print("=" * 65)

    # 1. Ground Truth
    print("\n[로드] 2월 시청 데이터...")
    gt = load_feb_ground_truth(args.parquet)
    print(f"  유저: {len(gt):,}명, 시청: {sum(len(v) for v in gt.values()):,}건")

    conn = get_connection()
    try:
        exclude_vods = load_exclude_vods(conn)
        series_map = load_series_episode_map(conn) if args.mode == "expanded" else None

        # 유저 세그먼트 준비
        segments: list[tuple[str, set[str] | None]] = [("전체", None)]
        if args.segment:
            print("\n[로드] 유저별 시청 횟수...")
            watch_counts = load_user_watch_counts(conn)
            cold = {uid for uid, cnt in watch_counts.items() if cnt < 5}
            warm = {uid for uid, cnt in watch_counts.items() if 5 <= cnt < 20}
            heavy = {uid for uid, cnt in watch_counts.items() if cnt >= 20}
            segments.extend([
                (f"콜드스타트(<5회, {len(cold):,}명)", cold),
                (f"웜(5~19회, {len(warm):,}명)", warm),
                (f"헤비(>=20회, {len(heavy):,}명)", heavy),
            ])

        # 2. 추천 데이터 로드 (1회)
        cf_recs = load_recommendations(conn, "COLLABORATIVE", exclude_vods)
        vs_recs = load_recommendations(conn, "VISUAL_SIMILARITY", exclude_vods)
        hybrid_recs = load_hybrid_recommendations(conn, exclude_vods)
        print(f"\n[추천 로드] CF: {len(cf_recs):,}명, VS: {len(vs_recs):,}명, Hybrid: {len(hybrid_recs):,}명")

    finally:
        conn.close()

    # 3. 세그먼트별 평가
    for seg_name, user_filter in segments:
        print("\n" + "=" * 65)
        print(f"[{seg_name}] Top-{args.top_k}, mode={args.mode}")
        print("=" * 65)

        cf_result = evaluate(cf_recs, gt, args.top_k, series_map, user_filter)
        vs_result = evaluate(vs_recs, gt, args.top_k, series_map, user_filter)
        hybrid_result = evaluate(hybrid_recs, gt, args.top_k, series_map, user_filter) if hybrid_recs else {"error": "N/A"}

        print(f"  eval_users: CF={cf_result.get('eval_users','?')}, VS={vs_result.get('eval_users','?')}, Hybrid={hybrid_result.get('eval_users','?')}")
        print(f"\n  {'지표':<18s} {'CF':>10s} {'VS':>10s} {'Hybrid':>10s}")
        print("  " + "-" * 52)
        for metric in ["hit_rate", "precision@k", "recall@k", "ndcg@k", "avg_matched"]:
            vals = []
            for r in [cf_result, vs_result, hybrid_result]:
                v = r.get(metric, "N/A")
                vals.append(f"{v:.4f}" if isinstance(v, (int, float)) else str(v))
            print(f"  {metric:<16s} {vals[0]:>10s} {vals[1]:>10s} {vals[2]:>10s}")
        print("  " + "=" * 52)


if __name__ == "__main__":
    main()
