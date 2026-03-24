"""
Vector Search 전체 파이프라인 (배치 행렬 연산 → DB 직접 적재)

PLAN_01 (content_score) + PLAN_02 (clip_score) + PLAN_03 (앙상블) + DB INSERT

사용법:
    python scripts/run_pipeline.py                # 전체 VOD 실행 + DB 적재
    python scripts/run_pipeline.py --dry-run      # DB 저장 없이 결과만 확인
    python scripts/run_pipeline.py --limit 100    # 테스트용 (100건만)
    python scripts/run_pipeline.py --alpha 0.6    # CLIP 가중치 override
    python scripts/run_pipeline.py --batch-size 500  # 배치 크기 조정
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2.extras
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ensemble import load_config
from src.db import get_connection

# 에피소드 단위 유지 대상 ct_cl (시리즈 중복 제거 제외)
_EPISODE_LEVEL_CT_CL = frozenset(["TV 연예/오락"])

DATA_DIR = Path(__file__).parent.parent / "data"
META_PARQUET = DATA_DIR / "meta_embeddings.parquet"
CLIP_PARQUET = DATA_DIR / "clip_embeddings.parquet"


def dump_embeddings_if_needed():
    """로컬 parquet 없으면 DB에서 자동 dump."""
    if META_PARQUET.exists() and CLIP_PARQUET.exists():
        return

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    print("[dump] 임베딩 parquet 없음 → DB에서 다운로드")
    conn = get_connection()
    try:
        cur = conn.cursor()

        print("[dump 1/2] vod_meta_embedding ...", end=" ", flush=True)
        cur.execute("""
            SELECT vme.vod_id_fk, vme.embedding
            FROM vod_meta_embedding vme
            JOIN vod v ON vme.vod_id_fk = v.full_asset_id
            JOIN vod_embedding ve ON vme.vod_id_fk = ve.vod_id_fk AND ve.model_name = 'clip-ViT-B-32'
            WHERE v.poster_url IS NOT NULL AND v.poster_url != ''
            ORDER BY vme.vod_id_fk
        """)
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=["vod_id_fk", "embedding"])
        df["embedding"] = df["embedding"].apply(list)
        df.to_parquet(META_PARQUET, index=False)
        print(f"{len(df):,}건")

        print("[dump 2/2] vod_embedding (CLIP) ...", end=" ", flush=True)
        cur.execute("""
            SELECT ve.vod_id_fk, ve.embedding
            FROM vod_embedding ve
            JOIN vod v ON ve.vod_id_fk = v.full_asset_id
            WHERE ve.model_name = 'clip-ViT-B-32'
              AND v.poster_url IS NOT NULL AND v.poster_url != ''
            ORDER BY ve.vod_id_fk
        """)
        rows = cur.fetchall()
        df = pd.DataFrame(rows, columns=["vod_id_fk", "embedding"])
        df["embedding"] = df["embedding"].apply(list)
        df.to_parquet(CLIP_PARQUET, index=False)
        print(f"{len(df):,}건")

        cur.close()
    finally:
        conn.close()


def load_embeddings():
    """로컬 parquet에서 벡터 로드 후 numpy 정규화."""
    dump_embeddings_if_needed()

    print("[로드] meta_embeddings.parquet ...", end=" ", flush=True)
    meta_df = pd.read_parquet(META_PARQUET)
    meta_vecs = np.array(meta_df["embedding"].tolist(), dtype=np.float32)
    meta_vecs /= np.linalg.norm(meta_vecs, axis=1, keepdims=True) + 1e-10
    print(f"{len(meta_df):,}건")

    print("[로드] clip_embeddings.parquet ...", end=" ", flush=True)
    clip_df = pd.read_parquet(CLIP_PARQUET)
    clip_vecs = np.array(clip_df["embedding"].tolist(), dtype=np.float32)
    clip_vecs /= np.linalg.norm(clip_vecs, axis=1, keepdims=True) + 1e-10
    print(f"{len(clip_df):,}건")

    clip_ids = clip_df["vod_id_fk"].values

    return meta_df, meta_vecs, clip_df, clip_vecs, clip_ids


def process_batch(
    batch_indices,
    meta_ids, meta_vecs,
    clip_ids, clip_vecs,
    clip_id2meta_idx,
    alpha, top_n,
    valid_clip_idx, valid_meta_idx,
    vod_series_map=None,
):
    """
    배치 단위 행렬 연산:
    batch_vecs (B, D) @ meta_vecs.T (D, N) → (B, N) 유사도 행렬 한 번에 계산
    """
    B = len(batch_indices)

    # PLAN_01: content_score 배치 행렬 곱 (B, N)
    batch_meta_vecs = meta_vecs[batch_indices]          # (B, 384)
    content_sim = batch_meta_vecs @ meta_vecs.T         # (B, N)

    # PLAN_02: clip_score 배치 행렬 곱 (B, M)
    # 배치 VOD 중 clip 임베딩 있는 것만 추출
    batch_vod_ids = meta_ids[batch_indices]
    clip_sim = np.zeros((B, len(clip_ids)), dtype=np.float32)
    for b_i, vod_id in enumerate(batch_vod_ids):
        if vod_id in clip_id2meta_idx:
            c_idx = clip_id2meta_idx[vod_id]
            clip_sim[b_i] = clip_vecs @ clip_vecs[c_idx]   # (M,)

    all_rows = []
    for b_i, vod_id in enumerate(batch_vod_ids):
        src_meta_idx = batch_indices[b_i]

        # clip_score를 meta 인덱스 기준으로 정렬 (numpy 인덱싱으로 한 번에 처리)
        clip_score_by_meta = np.zeros(len(meta_ids), dtype=np.float32)
        clip_score_by_meta[valid_meta_idx] = clip_sim[b_i, valid_clip_idx]

        # PLAN_03: 앙상블
        # clip 없거나 clip_score=1.0(동일 트레일러 = 시리즈물)이면 alpha=0 → content_score만 반영
        has_clip = clip_score_by_meta > 0.0
        eff_alpha = np.where(has_clip & (clip_score_by_meta < 1.0), alpha, 0.0)
        final_scores = eff_alpha * clip_score_by_meta + (1 - eff_alpha) * content_sim[b_i]

        # 자기 자신 제외
        final_scores[src_meta_idx] = -1.0

        # TOP-N 추출 (시리즈 중복 제거 적용)
        # 중복 제거 후 top_n 확보를 위해 넉넉하게 후보 추출
        raw_top_n = min(top_n * 3, len(final_scores))
        top_idx = np.argpartition(final_scores, -raw_top_n)[-raw_top_n:]
        top_idx = top_idx[np.argsort(final_scores[top_idx])[::-1]]

        seen_series: set[str] = set()
        rank = 0
        for idx in top_idx:
            candidate_id = meta_ids[idx]
            # 시리즈 중복 제거 (vod_series_map 있을 때만)
            if vod_series_map is not None:
                series_nm, ct_cl = vod_series_map.get(candidate_id, (candidate_id, ""))
                if ct_cl not in _EPISODE_LEVEL_CT_CL:
                    if series_nm in seen_series:
                        continue
                    seen_series.add(series_nm)

            rank += 1
            if rank > top_n:
                break
            all_rows.append({
                "source_vod_id": vod_id,
                "vod_id_fk": candidate_id,
                "rank": rank,
                "score": round(float(final_scores[idx]), 6),
                "clip_score": round(float(clip_score_by_meta[idx]), 6),
                "content_score": round(float(content_sim[b_i, idx]), 6),
                "recommendation_type": "CONTENT_BASED",
            })

    return all_rows


def export_to_db(records: list[dict], batch_size: int = 1000):
    """추천 결과를 serving.vod_recommendation에 직접 적재 (DELETE + INSERT)."""
    if not records:
        print("[DB] 저장할 레코드 없음")
        return

    conn = get_connection()
    cur = conn.cursor()

    # 기존 CONTENT_BASED 추천 삭제
    print("[DB] 기존 CONTENT_BASED 추천 삭제 중...")
    cur.execute("DELETE FROM serving.vod_recommendation WHERE recommendation_type = 'CONTENT_BASED'")
    print(f"  삭제: {cur.rowcount:,}건")

    # INSERT
    insert_sql = """
        INSERT INTO serving.vod_recommendation
            (source_vod_id, vod_id_fk, rank, score, recommendation_type)
        VALUES (%(source_vod_id)s, %(vod_id_fk)s, %(rank)s, %(score)s, %(recommendation_type)s)
    """
    total = 0
    for i in range(0, len(records), batch_size):
        batch = records[i:i + batch_size]
        psycopg2.extras.execute_batch(cur, insert_sql, batch, page_size=batch_size)
        total += len(batch)
        if total % 100000 < batch_size:
            print(f"  [{total:,}/{len(records):,}]")

    conn.commit()
    cur.close()
    conn.close()
    print(f"[DB] 적재 완료: {total:,}건")


def main():
    parser = argparse.ArgumentParser(description="Vector Search 전체 파이프라인 (배치 행렬 연산 → DB 적재)")
    parser.add_argument("--vod-id", default=None, help="특정 VOD만 처리")
    parser.add_argument("--limit", type=int, default=None, help="처리할 VOD 수 제한")
    parser.add_argument("--alpha", type=float, default=None, help="CLIP 가중치 override")
    parser.add_argument("--dry-run", action="store_true", help="DB 저장 없이 결과만 확인")
    parser.add_argument("--batch-size", type=int, default=1000, help="배치 크기 (기본 1000)")
    args = parser.parse_args()

    config = load_config()
    alpha = args.alpha if args.alpha is not None else config["ensemble"]["alpha"]
    top_n = config["ensemble"]["top_n"]

    print("=" * 60)
    print("Vector Search 파이프라인 시작 (배치 행렬 연산)")
    print(f"  alpha={alpha}, top_n={top_n}, batch_size={args.batch_size}")
    print("=" * 60)

    # VOD 시리즈 매핑 로드 (시리즈 중복 제거용)
    print("[로드] VOD 시리즈 매핑 ...", end=" ", flush=True)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT full_asset_id, series_nm, ct_cl FROM public.vod")
    vod_series_map = {
        row[0]: (row[1] or row[0], row[2] or "")
        for row in cur.fetchall()
    }
    cur.close()
    conn.close()
    print(f"{len(vod_series_map):,}건")

    # 벡터 로드 (로컬 parquet 없으면 자동 dump)
    meta_df, meta_vecs, clip_df, clip_vecs, clip_ids = load_embeddings()
    meta_ids = meta_df["vod_id_fk"].values

    # clip vod_id → clip 인덱스 매핑
    clip_id2meta_idx = {vid: i for i, vid in enumerate(clip_ids)}

    # clip_to_meta 사전 계산 (배치마다 재계산 방지)
    meta_id2idx = {vid: i for i, vid in enumerate(meta_ids)}
    clip_to_meta = np.array([meta_id2idx.get(cid, -1) for cid in clip_ids], dtype=np.int32)
    valid_mask = clip_to_meta >= 0
    valid_clip_idx = np.where(valid_mask)[0]
    valid_meta_idx = clip_to_meta[valid_mask]

    # 대상 VOD 인덱스
    if args.vod_id:
        indices = np.where(meta_ids == args.vod_id)[0]
    else:
        indices = np.arange(len(meta_ids))
        if args.limit:
            indices = indices[: args.limit]

    total = len(indices)
    print(f"\n[유사도 계산] 대상 {total:,}건")

    all_rows = []
    for start in range(0, total, args.batch_size):
        batch_indices = indices[start: start + args.batch_size]
        rows = process_batch(
            batch_indices, meta_ids, meta_vecs,
            clip_ids, clip_vecs, clip_id2meta_idx,
            alpha, top_n,
            valid_clip_idx, valid_meta_idx,
            vod_series_map=vod_series_map,
        )
        all_rows.extend(rows)
        done = min(start + args.batch_size, total)
        print(f"  [{done:,}/{total:,}] 누적 {len(all_rows):,}건")

    print("=" * 60)
    print(f"유사도 계산 완료: {len(all_rows):,}건")

    if args.dry_run:
        print("dry-run 모드 — DB 저장 생략")
    else:
        export_to_db(all_rows)

    print("=" * 60)


if __name__ == "__main__":
    main()
