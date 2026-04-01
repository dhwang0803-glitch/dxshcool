"""
VISUAL_SIMILARITY 유저 기반 시각 유사도 추천 파이프라인 (병렬 연산 + COPY 벌크 적재)

user_embedding CLIP 부분([:512])과 시리즈 대표 VOD CLIP 벡터 간
코사인 유사도를 멀티프로세스 배치 행렬 연산으로 계산하여
COPY 프로토콜로 serving.vod_recommendation에 벌크 적재한다.

사용법:
    python scripts/run_visual_similarity.py                  # 전체 유저 + DB 적재
    python scripts/run_visual_similarity.py --dry-run        # DB 저장 없이 결과만 확인
    python scripts/run_visual_similarity.py --limit 100      # 유저 100명만 (테스트)
    python scripts/run_visual_similarity.py --user-id X      # 특정 유저 1명
    python scripts/run_visual_similarity.py --batch-size 500  # 유저 배치 크기 조정
    python scripts/run_visual_similarity.py --workers 4      # 병렬 프로세스 수
"""
import argparse
import io
import os
import sys
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ensemble import load_config
from src.db import get_connection

DATA_DIR = Path(__file__).parent.parent / "data"
USER_CLIP_PARQUET = DATA_DIR / "user_clip_embeddings.parquet"
CLIP_PARQUET = DATA_DIR / "series_clip_embeddings.parquet"
WATCH_PARQUET = DATA_DIR / "watch_history_sparse.parquet"


# ─────────────────────────────── PHASE 1: DUMP ───────────────────────────────

def dump_user_clip_embeddings(min_vod_count: int = 3):
    """user_embedding에서 CLIP 512D 부분만 추출하여 parquet 저장."""
    if USER_CLIP_PARQUET.exists():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("[dump] user_clip_embeddings.parquet 생성 중...", end=" ", flush=True)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT user_id_fk, embedding
            FROM user_embedding
            WHERE vod_count >= %s
            """,
            (min_vod_count,),
        )
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=["user_id_fk", "embedding"])
        # 896D → [:512] CLIP 부분만 저장
        df["embedding"] = df["embedding"].apply(lambda v: list(v)[:512])
        df.to_parquet(USER_CLIP_PARQUET, index=False)
        print(f"{len(df):,}건")
        cur.close()
    finally:
        conn.close()


def dump_series_clip_embeddings():
    """시리즈 대표 VOD의 CLIP 벡터 parquet 저장 (run_pipeline.py와 공유)."""
    if CLIP_PARQUET.exists():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("[dump] series_clip_embeddings.parquet 생성 중...", end=" ", flush=True)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT ve.vod_id_fk, ve.embedding
            FROM vod_embedding ve
            JOIN vod_series_embedding se ON ve.vod_id_fk = se.representative_vod_id
            WHERE ve.model_name = 'clip-ViT-B-32'
              AND se.poster_url IS NOT NULL AND se.poster_url != ''
            ORDER BY ve.vod_id_fk
            """
        )
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=["vod_id_fk", "embedding"])
        df["embedding"] = df["embedding"].apply(list)
        df.to_parquet(CLIP_PARQUET, index=False)
        print(f"{len(df):,}건")
        cur.close()
    finally:
        conn.close()


def dump_watch_history():
    """watch_history를 parquet로 저장 (유저별 시청 VOD 제외용)."""
    if WATCH_PARQUET.exists():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("[dump] watch_history_sparse.parquet 생성 중...", end=" ", flush=True)
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT user_id_fk, vod_id_fk FROM watch_history")
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=["user_id_fk", "vod_id_fk"])
        df.to_parquet(WATCH_PARQUET, index=False)
        print(f"{len(df):,}건")
        cur.close()
    finally:
        conn.close()


def dump_all_if_needed(min_vod_count: int):
    """필요한 parquet 파일이 없으면 DB에서 자동 dump."""
    dump_user_clip_embeddings(min_vod_count)
    dump_series_clip_embeddings()
    dump_watch_history()


# ─────────────────────────────── PHASE 2: LOAD ───────────────────────────────

def load_embeddings():
    """parquet에서 벡터 로드 + L2 정규화."""
    print("[로드] user_clip_embeddings.parquet ...", end=" ", flush=True)
    user_df = pd.read_parquet(USER_CLIP_PARQUET)
    user_vecs = np.array(user_df["embedding"].tolist(), dtype=np.float32)
    user_norms = np.linalg.norm(user_vecs, axis=1, keepdims=True) + 1e-10
    user_vecs /= user_norms
    user_ids = user_df["user_id_fk"].values
    print(f"{len(user_df):,}건")

    print("[로드] series_clip_embeddings.parquet ...", end=" ", flush=True)
    clip_df = pd.read_parquet(CLIP_PARQUET)
    vod_vecs = np.array(clip_df["embedding"].tolist(), dtype=np.float32)
    vod_vecs /= np.linalg.norm(vod_vecs, axis=1, keepdims=True) + 1e-10
    vod_ids = clip_df["vod_id_fk"].values
    print(f"{len(clip_df):,}건")

    return user_ids, user_vecs, vod_ids, vod_vecs


def load_watch_map(vod_id2idx: dict) -> dict[str, np.ndarray]:
    """watch_history를 유저별 인덱스 배열로 변환."""
    print("[로드] watch_history_sparse.parquet ...", end=" ", flush=True)
    wh_df = pd.read_parquet(WATCH_PARQUET)
    watch_map: dict[str, list[int]] = defaultdict(list)
    for uid, vid in zip(wh_df["user_id_fk"], wh_df["vod_id_fk"]):
        idx = vod_id2idx.get(vid)
        if idx is not None:
            watch_map[uid].append(idx)
    # list → numpy array (벡터화 마스킹용)
    result = {uid: np.array(indices, dtype=np.int32) for uid, indices in watch_map.items()}
    print(f"{len(result):,}명")
    return result


# ─────────────────────────── PHASE 3: BATCH COMPUTE ──────────────────────────

def _process_batch_worker(args):
    """멀티프로세스 워커 — pickle 직렬화를 위해 top-level 함수로 정의.

    args: (batch_user_ids, batch_user_vecs, vod_ids, vod_vecs, watch_map, top_n)
    """
    batch_user_ids, batch_user_vecs, vod_ids, vod_vecs, watch_map, top_n = args
    B = len(batch_user_ids)

    # (B, 512) @ (512, V) → (B, V) 유사도 행렬
    sim_matrix = batch_user_vecs @ vod_vecs.T

    all_rows = []
    for b_i in range(B):
        user_id = batch_user_ids[b_i]
        scores = sim_matrix[b_i].copy()

        # 시청 이력 제외
        watched_indices = watch_map.get(user_id)
        if watched_indices is not None:
            scores[watched_indices] = -1.0

        # TOP-N 추출
        if len(scores) <= top_n:
            top_idx = np.argsort(scores)[::-1][:top_n]
        else:
            top_idx = np.argpartition(scores, -top_n)[-top_n:]
            top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]

        for rank, idx in enumerate(top_idx, 1):
            if scores[idx] <= 0:
                break
            all_rows.append((
                user_id,          # user_id_fk
                vod_ids[idx],     # vod_id_fk
                rank,             # rank
                round(min(float(scores[idx]), 1.0), 6),  # score
            ))

    return all_rows


# ─────────────────────────── PHASE 4: DB EXPORT (COPY) ───────────────────────

def export_to_db_copy(records: list[tuple]):
    """COPY 프로토콜로 serving.vod_recommendation에 벌크 적재.

    execute_batch 대비 5~10배 빠름.
    records: [(user_id_fk, vod_id_fk, rank, score), ...]
    """
    if not records:
        print("[DB] 저장할 레코드 없음")
        return

    conn = get_connection()
    cur = conn.cursor()

    # 기존 VISUAL_SIMILARITY 추천 삭제
    print("[DB] 기존 VISUAL_SIMILARITY 추천 삭제 중...")
    cur.execute(
        "DELETE FROM serving.vod_recommendation "
        "WHERE recommendation_type = 'VISUAL_SIMILARITY'"
    )
    print(f"  삭제: {cur.rowcount:,}건")
    conn.commit()

    # COPY용 CSV 버퍼 생성 (청크 단위)
    COPY_SQL = (
        "COPY serving.vod_recommendation "
        "(user_id_fk, source_vod_id, vod_id_fk, rank, score, recommendation_type) "
        "FROM STDIN WITH (FORMAT csv, NULL '\\N')"
    )
    CHUNK_SIZE = 100_000
    total = 0

    for chunk_start in range(0, len(records), CHUNK_SIZE):
        chunk = records[chunk_start:chunk_start + CHUNK_SIZE]
        buf = io.StringIO()
        for user_id, vod_id, rank, score in chunk:
            # CSV 행: user_id_fk, source_vod_id(NULL), vod_id_fk, rank, score, type
            buf.write(f"{user_id},\\N,{vod_id},{rank},{score},VISUAL_SIMILARITY\n")
        buf.seek(0)
        cur.copy_expert(COPY_SQL, buf)
        total += len(chunk)
        print(f"  [COPY {total:,}/{len(records):,}]")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[DB] 적재 완료: {total:,}건")


# ─────────────────────────── MAIN ────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="VISUAL_SIMILARITY 유저 기반 시각 유사도 추천 파이프라인"
    )
    parser.add_argument("--user-id", default=None, help="특정 유저만 처리")
    parser.add_argument("--limit", type=int, default=None, help="처리할 유저 수 제한")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 결과만 확인")
    parser.add_argument("--batch-size", type=int, default=1000, help="유저 배치 크기 (기본 1000)")
    parser.add_argument("--workers", type=int, default=None,
                        help="병렬 프로세스 수 (기본: CPU 코어 수 - 1)")
    args = parser.parse_args()

    config = load_config()
    vs_config = config["visual_similarity"]
    top_n = vs_config["top_n"]
    min_vod_count = vs_config["min_vod_count"]
    workers = args.workers or max(1, (os.cpu_count() or 4) - 1)

    print("=" * 60)
    print("VISUAL_SIMILARITY 파이프라인 시작 (병렬 연산 + COPY 벌크 적재)")
    print(f"  top_n={top_n}, min_vod_count={min_vod_count}")
    print(f"  batch_size={args.batch_size}, workers={workers}")
    print("=" * 60)

    # PHASE 1: dump
    dump_all_if_needed(min_vod_count)

    # PHASE 2: load
    user_ids, user_vecs, vod_ids, vod_vecs = load_embeddings()
    vod_id2idx = {vid: i for i, vid in enumerate(vod_ids)}
    watch_map = load_watch_map(vod_id2idx)

    # 대상 유저 필터
    if args.user_id:
        mask = user_ids == args.user_id
        if not mask.any():
            print(f"[오류] user_id '{args.user_id}' not found in user_clip_embeddings")
            return
        indices = np.where(mask)[0]
    else:
        indices = np.arange(len(user_ids))
        if args.limit:
            indices = indices[:args.limit]

    total = len(indices)
    print(f"\n[유사도 계산] 대상 유저 {total:,}명 (workers={workers})")

    # PHASE 3: 병렬 배치 연산
    # 배치 작업 목록 생성
    batch_args = []
    for start in range(0, total, args.batch_size):
        batch_idx = indices[start:start + args.batch_size]
        batch_user_ids = user_ids[batch_idx]
        batch_user_vecs = user_vecs[batch_idx]
        batch_args.append((
            batch_user_ids, batch_user_vecs,
            vod_ids, vod_vecs, watch_map, top_n,
        ))

    all_rows = []
    completed_batches = 0
    total_batches = len(batch_args)

    if workers == 1 or total_batches <= 1:
        # 단일 프로세스 (소규모 또는 --workers 1)
        for ba in batch_args:
            rows = _process_batch_worker(ba)
            all_rows.extend(rows)
            completed_batches += 1
            print(f"  [{completed_batches}/{total_batches}] 누적 {len(all_rows):,}건")
    else:
        # 멀티프로세스 병렬
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(_process_batch_worker, ba): i
                for i, ba in enumerate(batch_args)
            }
            for future in as_completed(futures):
                rows = future.result()
                all_rows.extend(rows)
                completed_batches += 1
                if completed_batches % 10 == 0 or completed_batches == total_batches:
                    print(f"  [{completed_batches}/{total_batches}] 누적 {len(all_rows):,}건")

    print("=" * 60)
    print(f"유사도 계산 완료: {len(all_rows):,}건 ({total:,}명 × top_{top_n})")

    # PHASE 4: export
    if args.dry_run:
        print("dry-run 모드 — DB 저장 생략")
        if all_rows:
            print("\n[샘플 결과]")
            for uid, vid, rank, score in all_rows[:5]:
                print(f"  user={uid[:16]}... → vod={vid} rank={rank} score={score}")
    else:
        export_to_db_copy(all_rows)

    print("=" * 60)


if __name__ == "__main__":
    main()
