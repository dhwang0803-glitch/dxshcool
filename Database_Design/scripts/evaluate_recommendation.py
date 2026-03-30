"""
추천 엔진 오프라인 평가 스크립트

1월 학습 데이터 기반 추천 결과 vs 2월 실제 시청 데이터 비교.
- CF_Engine (COLLABORATIVE) + Vector_Search (CONTENT_BASED) 각각 평가
- TMDB_NEW_2025 등 원본 데이터에 없던 VOD는 평가에서 제외

평가 지표:
- Hit Rate: 추천 목록에 1건이라도 맞은 유저 비율
- Precision@K: 추천 K개 중 실제 시청 VOD 비율
- Recall@K: 실제 시청 VOD 중 추천 목록에 포함된 비율
- NDCG@K: 순위 가중 정확도

사용법:
    python scripts/evaluate_recommendation.py
    python scripts/evaluate_recommendation.py --top-k 10
    python scripts/evaluate_recommendation.py --parquet /path/to/202302.parquet
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

DEFAULT_PARQUET = str(Path(__file__).parent.parent / "data" / "202302_watch_history.parquet")

# 평가에서 제외할 rag_source 목록 (원본 2023 데이터에 없던 VOD)
EXCLUDE_RAG_SOURCES = frozenset(["TMDB_NEW_2025"])


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_exclude_vods(conn) -> set[str]:
    """평가 제외 대상 VOD (TMDB_NEW_2025 등) 로드."""
    cur = conn.cursor()
    placeholders = ",".join(["%s"] * len(EXCLUDE_RAG_SOURCES))
    cur.execute(
        f"SELECT full_asset_id FROM public.vod WHERE rag_source IN ({placeholders})",
        tuple(EXCLUDE_RAG_SOURCES),
    )
    exclude = {row[0] for row in cur.fetchall()}
    cur.close()
    print(f"[필터] 평가 제외 VOD: {len(exclude):,}건 ({', '.join(EXCLUDE_RAG_SOURCES)})")
    return exclude


def load_recommendations(conn, rec_type: str, exclude_vods: set[str]) -> dict[str, list[str]]:
    """
    DB에서 추천 결과 로드.
    CF: user_id_fk 기준, Vector: source_vod_id 기준.
    """
    cur = conn.cursor()

    if rec_type == "COLLABORATIVE":
        cur.execute("""
            SELECT user_id_fk, vod_id_fk, rank
            FROM serving.vod_recommendation
            WHERE recommendation_type = %s
              AND user_id_fk IS NOT NULL
            ORDER BY user_id_fk, rank
        """, (rec_type,))
        recs: dict[str, list[str]] = {}
        for user_id, vod_id, rank in cur.fetchall():
            if vod_id in exclude_vods:
                continue
            recs.setdefault(user_id, []).append(vod_id)
    else:
        # CONTENT_BASED: source_vod_id → recommended vod_id_fk
        cur.execute("""
            SELECT source_vod_id, vod_id_fk, rank
            FROM serving.vod_recommendation
            WHERE recommendation_type = %s
              AND source_vod_id IS NOT NULL
            ORDER BY source_vod_id, rank
        """, (rec_type,))
        recs = {}
        for source_id, vod_id, rank in cur.fetchall():
            if vod_id in exclude_vods:
                continue
            recs.setdefault(source_id, []).append(vod_id)

    cur.close()
    return recs


def load_feb_ground_truth(parquet_path: str) -> dict[str, set[str]]:
    """2월 parquet에서 유저별 실제 시청 VOD 집합 로드."""
    df = pd.read_parquet(parquet_path, columns=["user_id_fk", "vod_id_fk"])
    ground_truth: dict[str, set[str]] = {}
    for user_id, vod_id in zip(df["user_id_fk"], df["vod_id_fk"]):
        ground_truth.setdefault(user_id, set()).add(vod_id)
    return ground_truth


def dcg_at_k(ranked_list: list[str], relevant: set[str], k: int) -> float:
    """DCG@K 계산."""
    dcg = 0.0
    for i, item in enumerate(ranked_list[:k]):
        if item in relevant:
            dcg += 1.0 / math.log2(i + 2)  # i+2 because log2(1)=0
    return dcg


def ndcg_at_k(ranked_list: list[str], relevant: set[str], k: int) -> float:
    """NDCG@K 계산."""
    dcg = dcg_at_k(ranked_list, relevant, k)
    # ideal DCG: 관련 아이템이 모두 상위에 있는 경우
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_hits))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def evaluate_cf(
    cf_recs: dict[str, list[str]],
    ground_truth: dict[str, set[str]],
    top_k: int,
) -> dict:
    """CF 추천 평가: 유저별 추천 vs 2월 실제 시청."""
    # 평가 대상: CF 추천이 있고 & 2월에도 시청 이력이 있는 유저
    eval_users = set(cf_recs.keys()) & set(ground_truth.keys())

    if not eval_users:
        return {"error": "평가 대상 유저 없음"}

    hits = 0
    total_precision = 0.0
    total_recall = 0.0
    total_ndcg = 0.0

    for user_id in eval_users:
        rec_list = cf_recs[user_id][:top_k]
        actual = ground_truth[user_id]

        rec_set = set(rec_list)
        matched = rec_set & actual

        if matched:
            hits += 1

        precision = len(matched) / len(rec_list) if rec_list else 0.0
        recall = len(matched) / len(actual) if actual else 0.0
        ndcg = ndcg_at_k(rec_list, actual, top_k)

        total_precision += precision
        total_recall += recall
        total_ndcg += ndcg

    n = len(eval_users)
    return {
        "eval_users": n,
        "hit_rate": round(hits / n, 4),
        "precision@k": round(total_precision / n, 4),
        "recall@k": round(total_recall / n, 4),
        "ndcg@k": round(total_ndcg / n, 4),
        "avg_matched": round(sum(
            len(set(cf_recs[u][:top_k]) & ground_truth[u])
            for u in eval_users
        ) / n, 2),
    }


def evaluate_vector(
    vec_recs: dict[str, list[str]],
    ground_truth: dict[str, set[str]],
    top_k: int,
) -> dict:
    """
    Vector_Search 평가: 유저가 1월에 본 VOD의 유사 추천 vs 2월 실제 시청.
    source_vod_id가 유저의 1월 시청 VOD인 경우, 그 추천 목록과 2월 시청을 비교.
    """
    # 1월 유저별 시청 VOD 필요 → DB에서 로드해야 함
    # 여기서는 ground_truth의 유저 기준으로, 해당 유저가 시청했을 법한 VOD의 추천을 평가
    # Vector_Search는 VOD→VOD 추천이므로 유저 단위 평가가 다름

    # 방법: 2월에 유저가 본 VOD가 "1월에 본 VOD의 유사 추천 목록"에 있었는지
    # 이를 위해 1월 시청 이력이 필요
    return {"note": "Vector_Search는 VOD→VOD 추천으로, 별도 1월 시청 이력 기반 평가 필요 (아래 evaluate_vector_with_jan 참조)"}


def evaluate_vector_with_jan(
    vec_recs: dict[str, list[str]],
    ground_truth: dict[str, set[str]],
    conn,
    top_k: int,
) -> dict:
    """
    Vector_Search 평가 (1월 시청 이력 활용):
    1) 유저가 1월에 본 VOD 목록 조회
    2) 각 VOD의 유사 추천 목록 합산 → 유저별 추천 풀 구성
    3) 2월 실제 시청과 비교
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id_fk, vod_id_fk
        FROM public.watch_history
        WHERE strt_dt >= '2023-01-01' AND strt_dt < '2023-02-01'
    """)
    jan_history: dict[str, set[str]] = {}
    for user_id, vod_id in cur.fetchall():
        jan_history.setdefault(user_id, set()).add(vod_id)
    cur.close()

    # 평가 대상: 1월 시청 있고 & 2월 시청 있는 유저
    eval_users = set(jan_history.keys()) & set(ground_truth.keys())

    if not eval_users:
        return {"error": "평가 대상 유저 없음"}

    hits = 0
    total_precision = 0.0
    total_recall = 0.0
    total_ndcg = 0.0

    for user_id in eval_users:
        # 유저가 1월에 본 VOD들의 유사 추천 합산 (중복 제거, 1월 시청 VOD 자체 제외)
        jan_vods = jan_history[user_id]
        score_map: dict[str, float] = {}  # vod_id → best_rank (낮을수록 좋음)

        for jan_vod in jan_vods:
            if jan_vod not in vec_recs:
                continue
            for rank_idx, rec_vod in enumerate(vec_recs[jan_vod][:top_k]):
                if rec_vod in jan_vods:
                    continue  # 이미 1월에 본 건 제외
                # 여러 source에서 추천된 경우 최고 순위(최소 rank) 유지
                if rec_vod not in score_map or rank_idx < score_map[rec_vod]:
                    score_map[rec_vod] = rank_idx

        if not score_map:
            continue

        # 순위순 정렬 → top_k 추출
        sorted_recs = sorted(score_map.keys(), key=lambda v: score_map[v])[:top_k]
        actual = ground_truth[user_id]

        matched = set(sorted_recs) & actual
        if matched:
            hits += 1

        precision = len(matched) / len(sorted_recs) if sorted_recs else 0.0
        recall = len(matched) / len(actual) if actual else 0.0
        ndcg = ndcg_at_k(sorted_recs, actual, top_k)

        total_precision += precision
        total_recall += recall
        total_ndcg += ndcg

    n = len(eval_users)
    if n == 0:
        return {"error": "유효 평가 유저 없음 (1월 시청 VOD가 추천에 없음)"}

    return {
        "eval_users": n,
        "hit_rate": round(hits / n, 4),
        "precision@k": round(total_precision / n, 4),
        "recall@k": round(total_recall / n, 4),
        "ndcg@k": round(total_ndcg / n, 4),
    }


def load_hybrid_recommendations(conn, exclude_vods: set[str]) -> dict[str, list[str]]:
    """serving.hybrid_recommendation에서 유저별 추천 로드 (rank 순)."""
    cur = conn.cursor()
    cur.execute("""
        SELECT user_id_fk, vod_id_fk, rank
        FROM serving.hybrid_recommendation
        ORDER BY user_id_fk, rank
    """)
    recs: dict[str, list[str]] = {}
    for user_id, vod_id, rank in cur.fetchall():
        if vod_id in exclude_vods:
            continue
        recs.setdefault(user_id, []).append(vod_id)
    cur.close()
    return recs


def main():
    parser = argparse.ArgumentParser(description="추천 엔진 오프라인 평가")
    parser.add_argument("--parquet", default=DEFAULT_PARQUET, help="2월 watch_history parquet 경로")
    parser.add_argument("--top-k", type=int, default=20, help="평가 기준 K (기본 20)")
    args = parser.parse_args()

    if not os.path.exists(args.parquet):
        print(f"[ERROR] parquet 없음: {args.parquet}")
        print("  먼저 실행: python scripts/test_data_upload.py")
        sys.exit(1)

    print("=" * 60)
    print("추천 엔진 오프라인 평가")
    print(f"  2월 데이터: {args.parquet}")
    print(f"  Top-K: {args.top_k}")
    print(f"  제외 rag_source: {', '.join(EXCLUDE_RAG_SOURCES)}")
    print("=" * 60)

    # 1. 2월 ground truth 로드
    print("\n[로드] 2월 시청 데이터...")
    ground_truth = load_feb_ground_truth(args.parquet)
    total_feb_views = sum(len(v) for v in ground_truth.values())
    print(f"  유저: {len(ground_truth):,}명, 시청: {total_feb_views:,}건")

    conn = get_connection()
    try:
        # 2. 제외 VOD 로드
        exclude_vods = load_exclude_vods(conn)

        # 3. CF 평가
        print("\n" + "-" * 60)
        print("[CF_Engine] COLLABORATIVE 추천 평가")
        print("-" * 60)
        cf_recs = load_recommendations(conn, "COLLABORATIVE", exclude_vods)
        print(f"  추천 유저: {len(cf_recs):,}명")

        cf_result = evaluate_cf(cf_recs, ground_truth, args.top_k)
        for k, v in cf_result.items():
            print(f"  {k}: {v}")

        # 4. Vector_Search 평가
        print("\n" + "-" * 60)
        print("[Vector_Search] CONTENT_BASED 추천 평가")
        print("-" * 60)
        vec_recs = load_recommendations(conn, "CONTENT_BASED", exclude_vods)
        print(f"  추천 source VOD: {len(vec_recs):,}건")

        vec_result = evaluate_vector_with_jan(
            vec_recs, ground_truth, conn, args.top_k
        )
        for k, v in vec_result.items():
            print(f"  {k}: {v}")

        # 5. Hybrid 평가
        print("\n" + "-" * 60)
        print("[Hybrid_Layer] hybrid_recommendation 평가")
        print("-" * 60)
        hybrid_recs = load_hybrid_recommendations(conn, exclude_vods)
        print(f"  추천 유저: {len(hybrid_recs):,}명")

        if hybrid_recs:
            hybrid_result = evaluate_cf(hybrid_recs, ground_truth, args.top_k)
            for k, v in hybrid_result.items():
                print(f"  {k}: {v}")
        else:
            hybrid_result = {"error": "hybrid_recommendation 데이터 없음"}
            print("  [WARN] serving.hybrid_recommendation 테이블이 비어 있습니다.")

    finally:
        conn.close()

    # 6. 요약
    print("\n" + "=" * 60)
    print(f"평가 요약 (Top-{args.top_k})")
    print("=" * 60)
    print(f"{'지표':<20s} {'CF':>10s} {'Vector':>10s} {'Hybrid':>10s}")
    print("-" * 54)
    for metric in ["hit_rate", "precision@k", "recall@k", "ndcg@k"]:
        cf_val = cf_result.get(metric, "N/A")
        vec_val = vec_result.get(metric, "N/A")
        hyb_val = hybrid_result.get(metric, "N/A")
        cf_str = f"{cf_val:.4f}" if isinstance(cf_val, float) else str(cf_val)
        vec_str = f"{vec_val:.4f}" if isinstance(vec_val, float) else str(vec_val)
        hyb_str = f"{hyb_val:.4f}" if isinstance(hyb_val, float) else str(hyb_val)
        print(f"  {metric:<18s} {cf_str:>10s} {vec_str:>10s} {hyb_str:>10s}")
    print("=" * 60)


if __name__ == "__main__":
    main()
