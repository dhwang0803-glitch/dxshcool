"""user_embedding K-means 클러스터링 탐색 — 유저 세그먼트 분석.

DB 왕복:
  읽기 1: user_embedding (vod_count >= 20)        — server-side cursor
  읽기 2: watch_history + vod genre_detail JOIN   — server-side cursor
  쓰기:   없음 (파일 저장만)

Usage:
    python gen_rec_sentence/scripts/cluster_users.py
    python gen_rec_sentence/scripts/cluster_users.py --k 5
    python gen_rec_sentence/scripts/cluster_users.py --k 5 --skip-elbow
"""

import argparse
import json
import logging
import os
import sys

import numpy as np
import pandas as pd
import psycopg2.extras

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv

load_dotenv(".env")

from gen_rec_sentence.src.context_builder import get_conn

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_SEGMENTS_PATH = os.path.normpath(os.path.join(_BASE_DIR, "user_segments.json"))
_ASSIGNMENTS_PATH = os.path.normpath(os.path.join(_BASE_DIR, "cluster_assignments.parquet"))

_MIN_VOD_COUNT = 20
_PCA_N_COMPONENTS = 50
_DEFAULT_K_RANGE = (2, 7)
_MBKM_BATCH_SIZE = 10_000
_MBKM_RANDOM_STATE = 42
_TOP_GENRE_N = 10
_REPR_USER_N = 5
_CURSOR_ITERSIZE = 50_000


# ── Step 1: user_embedding 조회 ────────────────────────────────────────────────

def fetch_user_embeddings(conn) -> tuple[list[str], np.ndarray]:
    log.info("[1/5] user_embedding 조회 중 (vod_count >= %d)...", _MIN_VOD_COUNT)
    user_ids = []
    vectors = []

    with conn.cursor("ue_cursor", cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.itersize = _CURSOR_ITERSIZE
        cur.execute(
            """
            SELECT user_id_fk, embedding
            FROM public.user_embedding
            WHERE vod_count >= %s
            ORDER BY user_id_fk
            """,
            (_MIN_VOD_COUNT,),
        )
        for row in cur:
            vec = _parse_vector(row["embedding"])
            if vec is None or len(vec) != 896:
                continue
            user_ids.append(row["user_id_fk"])
            vectors.append(vec)

    X = np.array(vectors, dtype=np.float32)
    log.info("  → 유저 %d명 | shape: %s", len(user_ids), X.shape)
    return user_ids, X


def _parse_vector(raw) -> list[float] | None:
    if raw is None:
        return None
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        s = raw.strip().strip("[]")
        parts = [p.strip() for p in s.split(",") if p.strip()]
        try:
            return [float(p) for p in parts]
        except ValueError:
            return None
    try:
        return list(np.array(raw, dtype=float))
    except Exception:
        return None


# ── Step 2: PCA ────────────────────────────────────────────────────────────────

def run_pca(X: np.ndarray, n_components: int) -> np.ndarray:
    from sklearn.decomposition import PCA

    log.info("[2/5] PCA (%dd → %dd)...", X.shape[1], n_components)
    pca = PCA(n_components=n_components, random_state=_MBKM_RANDOM_STATE)
    X_pca = pca.fit_transform(X)

    cumvar = np.cumsum(pca.explained_variance_ratio_)
    log.info(
        "  explained_variance 누적: PC10=%.3f  PC20=%.3f  PC30=%.3f  PC50=%.3f",
        cumvar[9], cumvar[19], cumvar[29], cumvar[min(49, n_components - 1)],
    )
    return X_pca


# ── Step 3: Elbow curve ────────────────────────────────────────────────────────

def run_elbow(X_pca: np.ndarray, k_min: int, k_max: int) -> None:
    from sklearn.cluster import MiniBatchKMeans

    log.info("[3/5] Elbow curve (k=%d~%d)...", k_min, k_max)
    inertias = {}
    for k in range(k_min, k_max + 1):
        km = MiniBatchKMeans(
            n_clusters=k, batch_size=_MBKM_BATCH_SIZE,
            random_state=_MBKM_RANDOM_STATE, n_init=3,
        )
        km.fit(X_pca)
        inertias[k] = float(km.inertia_)
        log.info("  k=%d  inertia=%.2f", k, km.inertia_)

    print("\n─── Elbow Curve ─────────────────────────────")
    print(f"{'k':>4}  {'inertia':>16}  {'delta':>14}")
    prev = None
    for k, val in sorted(inertias.items()):
        delta_str = f"{val - prev:+.2f}" if prev is not None else "—"
        print(f"{k:>4}  {val:>16.2f}  {delta_str:>14}")
        prev = val
    print("─────────────────────────────────────────────\n")


# ── Step 4: 최종 클러스터링 ────────────────────────────────────────────────────

def run_clustering(X_pca: np.ndarray, k: int) -> np.ndarray:
    from sklearn.cluster import MiniBatchKMeans

    log.info("[4/5] 최종 클러스터링 k=%d...", k)
    km = MiniBatchKMeans(
        n_clusters=k, batch_size=_MBKM_BATCH_SIZE,
        random_state=_MBKM_RANDOM_STATE, n_init=5,
    )
    labels = km.fit_predict(X_pca).astype(np.int32)

    unique, counts = np.unique(labels, return_counts=True)
    for cid, cnt in zip(unique, counts):
        log.info("  cluster %d: %d명 (%.1f%%)", cid, cnt, cnt / len(labels) * 100)
    return labels


# ── Step 5: 클러스터별 genre_detail 분포 분석 ──────────────────────────────────

def fetch_genre_dist(
    conn, user_ids: list[str], labels: np.ndarray
) -> dict[int, dict[str, float]]:
    log.info("[5/5] 클러스터별 genre_detail 분포 분석 중...")

    uid_to_cluster = {uid: int(labels[i]) for i, uid in enumerate(user_ids)}
    n_clusters = int(labels.max()) + 1
    cluster_counts: dict[int, dict[str, int]] = {c: {} for c in range(n_clusters)}

    with conn.cursor("genre_cur", cursor_factory=psycopg2.extras.DictCursor) as cur:
        cur.itersize = _CURSOR_ITERSIZE
        cur.execute(
            """
            SELECT wh.user_id_fk, v.genre_detail
            FROM public.watch_history wh
            JOIN public.vod v ON v.full_asset_id = wh.vod_id_fk
            WHERE wh.user_id_fk = ANY(%s)
              AND v.genre_detail IS NOT NULL
              AND v.genre_detail != ''
            """,
            (user_ids,),
        )
        for row in cur:
            cid = uid_to_cluster.get(row["user_id_fk"])
            g = row["genre_detail"].strip()
            if cid is None or not g:
                continue
            cluster_counts[cid][g] = cluster_counts[cid].get(g, 0) + 1

    genre_dist: dict[int, dict[str, float]] = {}
    for cid, counts in cluster_counts.items():
        total = sum(counts.values())
        if total == 0:
            genre_dist[cid] = {}
            continue
        top = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:_TOP_GENRE_N]
        genre_dist[cid] = {g: round(cnt / total, 4) for g, cnt in top}

    return genre_dist


def fetch_repr_users(
    conn, user_ids: list[str], labels: np.ndarray, k: int
) -> dict[int, list[dict]]:
    repr_users: dict[int, list[dict]] = {c: [] for c in range(k)}

    for cid in range(k):
        sample_uids = [user_ids[i] for i, l in enumerate(labels) if l == cid][:_REPR_USER_N]
        if not sample_uids:
            continue

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT wh.user_id_fk, v.genre_detail, COUNT(*) AS cnt
                FROM public.watch_history wh
                JOIN public.vod v ON v.full_asset_id = wh.vod_id_fk
                WHERE wh.user_id_fk = ANY(%s)
                  AND v.genre_detail IS NOT NULL AND v.genre_detail != ''
                GROUP BY wh.user_id_fk, v.genre_detail
                ORDER BY wh.user_id_fk, cnt DESC
                """,
                (sample_uids,),
            )
            rows = cur.fetchall()

        user_genre_map: dict[str, list[str]] = {}
        for uid, genre, _ in rows:
            if uid not in user_genre_map:
                user_genre_map[uid] = []
            if len(user_genre_map[uid]) < 5:
                user_genre_map[uid].append(genre)

        repr_users[cid] = [
            {"user_id": uid[:12] + "...", "top_genres": genres}
            for uid, genres in user_genre_map.items()
        ]

    return repr_users


# ── 저장 + 출력 ────────────────────────────────────────────────────────────────

def save_results(
    user_ids: list[str],
    labels: np.ndarray,
    genre_dist: dict[int, dict[str, float]],
    repr_users: dict[int, list[dict]],
    k: int,
) -> list[dict]:
    os.makedirs(_BASE_DIR, exist_ok=True)

    segments = []
    for cid in range(k):
        segments.append({
            "cluster_id": cid,
            "user_count": int(np.sum(labels == cid)),
            "genre_detail_dist": genre_dist.get(cid, {}),
            "repr_users": repr_users.get(cid, []),
            "label": "",  # 사람이 직접 결정
        })

    with open(_SEGMENTS_PATH, "w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=False, indent=2)
    log.info("저장: %s", _SEGMENTS_PATH)

    pd.DataFrame({"user_id": user_ids, "cluster_id": labels}).to_parquet(
        _ASSIGNMENTS_PATH, index=False
    )
    log.info("저장: %s", _ASSIGNMENTS_PATH)

    return segments


def print_summary(segments: list[dict], total_users: int) -> None:
    print("\n══════════ 클러스터 세그먼트 요약 ══════════")
    for seg in segments:
        cid = seg["cluster_id"]
        cnt = seg["user_count"]
        pct = cnt / total_users * 100 if total_users else 0
        top5 = list(seg["genre_detail_dist"].items())[:5]
        genre_str = "  |  ".join(f"{g}: {v*100:.1f}%" for g, v in top5)
        print(f"\n[Cluster {cid}]  {cnt:,}명 ({pct:.1f}%)")
        print(f"  Top 장르: {genre_str}")
        print(f"  label: (미정 — user_segments.json에서 직접 입력)")
    print("\n════════════════════════════════════════════\n")
    print(f"※ {_SEGMENTS_PATH} 의 label 필드를 채워주세요.")


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="user_embedding K-means 클러스터링")
    parser.add_argument("--k", type=int, default=None, help="클러스터 수 직접 지정")
    parser.add_argument("--k-range", type=int, nargs=2, default=[2, 7], metavar=("MIN", "MAX"))
    parser.add_argument("--pca-components", type=int, default=_PCA_N_COMPONENTS)
    parser.add_argument("--skip-elbow", action="store_true")
    args = parser.parse_args()

    conn = get_conn()
    try:
        user_ids, X = fetch_user_embeddings(conn)
        if not user_ids:
            log.error("조건에 맞는 유저 없음. 종료.")
            return

        X_pca = run_pca(X, n_components=args.pca_components)

        if not args.skip_elbow:
            run_elbow(X_pca, k_min=args.k_range[0], k_max=args.k_range[1])

        k = args.k
        if k is None:
            try:
                k = int(input("최적 k 입력: ").strip())
            except (ValueError, EOFError):
                log.warning("입력 없음 — 기본값 k=5 사용")
                k = 5

        labels = run_clustering(X_pca, k=k)
        genre_dist = fetch_genre_dist(conn, user_ids, labels)
        repr_users = fetch_repr_users(conn, user_ids, labels, k=k)
        segments = save_results(user_ids, labels, genre_dist, repr_users, k=k)
        print_summary(segments, total_users=len(user_ids))

    finally:
        conn.close()


if __name__ == "__main__":
    main()
