"""Colab 오프라인 배치용 데이터 추출.

VPC DB에서 추천 풀 VOD 메타데이터를 parquet으로 내보낸다.
Colab에서 DB 직접 접속이 불가할 때 사용.

Usage:
    python gen_rec_sentence/scripts/export_for_colab.py
    python gen_rec_sentence/scripts/export_for_colab.py --out-dir gen_rec_sentence/data/colab_data
"""

import argparse
import logging
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(".env")

from gen_rec_sentence.src.context_builder import get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Colab용 VOD 컨텍스트 parquet 추출")
    parser.add_argument("--out-dir", default="gen_rec_sentence/data/colab_data")
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    conn = get_conn()

    try:
        # ── 1) 추천 풀 VOD 목록 ──
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT vod_id_fk FROM (
                    SELECT vod_id_fk FROM serving.hybrid_recommendation
                    UNION
                    SELECT vod_id_fk FROM serving.popular_by_age
                ) t
            """)
            pool_vods = [r[0] for r in cur.fetchall()]
        log.info("추천 풀 VOD: %d건", len(pool_vods))

        # ── 2) VOD 메타데이터 조회 (embedding 제외) ──
        with conn.cursor() as cur:
            cur.execute("""
                SELECT v.full_asset_id, v.asset_nm, v.ct_cl, v.genre, v.genre_detail,
                       v.director, v.cast_lead, v.smry, v.rating
                FROM public.vod v
                WHERE v.full_asset_id = ANY(%s)
                  AND v.smry IS NOT NULL AND v.smry != ''
            """, (pool_vods,))
            rows = cur.fetchall()

        df = pd.DataFrame(rows, columns=[
            "vod_id", "asset_nm", "ct_cl", "genre", "genre_detail",
            "director", "cast_lead", "smry", "rating",
        ])
        # None → 빈 문자열
        for col in df.columns:
            df[col] = df[col].fillna("")

        ctx_path = os.path.join(args.out_dir, "vod_contexts.parquet")
        df.to_parquet(ctx_path, index=False)
        log.info("VOD 컨텍스트 저장: %s (%d건, %.1fMB)",
                 ctx_path, len(df), os.path.getsize(ctx_path) / 1024 / 1024)

        # ── 3) 기존 생성 쌍 (증분 처리용) ──
        with conn.cursor() as cur:
            cur.execute("""
                SELECT vod_id_fk, segment_id
                FROM serving.rec_sentence
                WHERE vod_id_fk = ANY(%s)
            """, (pool_vods,))
            existing = cur.fetchall()

        if existing:
            df_existing = pd.DataFrame(existing, columns=["vod_id", "segment_id"])
            exist_path = os.path.join(args.out_dir, "existing_pairs.parquet")
            df_existing.to_parquet(exist_path, index=False)
            log.info("기존 쌍 저장: %s (%d건)", exist_path, len(df_existing))
        else:
            log.info("기존 생성 쌍 없음 (첫 실행)")

        # ── 요약 ──
        n_segments = 5
        n_existing = len(existing)
        n_total = len(df) * n_segments
        log.info("")
        log.info("=== 추출 완료 ===")
        log.info("  VOD 컨텍스트: %d건", len(df))
        log.info("  전체 생성 대상: %d쌍 (VOD × %d seg)", n_total, n_segments)
        log.info("  기존 생성 쌍: %d건 → 실제 생성: %d쌍", n_existing, n_total - n_existing)
        log.info("  출력 경로: %s", args.out_dir)
        log.info("")
        log.info("다음 단계: Google Drive에 %s 폴더 업로드", args.out_dir)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
