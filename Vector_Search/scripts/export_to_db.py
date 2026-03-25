"""
앙상블 결과 parquet 저장 스크립트

사용법:
    # 전체 VOD 처리 후 parquet 저장
    python scripts/export_to_db.py

    # 특정 VOD만 처리
    python scripts/export_to_db.py --vod-id <full_asset_id>

    # 처리 건수 제한 (테스트용)
    python scripts/export_to_db.py --limit 100

    # 출력 파일 경로 지정
    python scripts/export_to_db.py --out-file data/recommendations.parquet
"""
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db import get_connection
from src.content_based import get_similar_by_meta
from src.clip_based import get_similar_by_clip
from src.ensemble import ensemble_scores, load_config

# 에피소드 단위 유지 대상 ct_cl (시리즈 중복 제거 제외)
_EPISODE_LEVEL_CT_CL = frozenset(["TV 연예/오락"])


def process_vod(vod_id: str, conn, alpha: float, top_n: int,
                vod_series_map: dict | None = None) -> list[dict]:
    # 시리즈 중복 제거 후 top_n 확보를 위해 넉넉하게 후보 수집
    raw_top_n = top_n * 3
    content_results = get_similar_by_meta(vod_id, conn, top_n=raw_top_n)
    clip_results = get_similar_by_clip(vod_id, conn, top_n=raw_top_n)
    results = ensemble_scores(clip_results, content_results, alpha=alpha, top_n=raw_top_n)

    rows = []
    seen_series: set[str] = set()
    rank = 0
    for r in results:
        candidate_id = r["vod_id"]
        # 시리즈 중복 제거
        if vod_series_map is not None:
            series_nm, ct_cl = vod_series_map.get(candidate_id, (candidate_id, ""))
            if ct_cl not in _EPISODE_LEVEL_CT_CL:
                if series_nm in seen_series:
                    continue
                seen_series.add(series_nm)

        rank += 1
        if rank > top_n:
            break
        rows.append({
            "source_vod_id": vod_id,
            "vod_id_fk": candidate_id,
            "rank": rank,
            "score": r["final_score"],
            "clip_score": r["clip_score"],
            "content_score": r["content_score"],
            "recommendation_type": "CONTENT_BASED",
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="앙상블 결과 parquet 저장")
    parser.add_argument("--vod-id", default=None, help="특정 VOD만 처리")
    parser.add_argument("--limit", type=int, default=None, help="처리할 VOD 수 제한")
    parser.add_argument("--out-file", default=None, help="출력 parquet 경로")
    args = parser.parse_args()

    config = load_config()
    alpha = config["ensemble"]["alpha"]
    top_n = config["ensemble"]["top_n"]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_file = args.out_file or f"data/recommendations_{timestamp}.parquet"
    Path(out_file).parent.mkdir(parents=True, exist_ok=True)

    conn = get_connection()
    try:
        # VOD 시리즈 매핑 로드 (시리즈 중복 제거용)
        cur = conn.cursor()
        cur.execute("SELECT full_asset_id, series_nm, ct_cl FROM public.vod")
        vod_series_map = {
            row[0]: (row[1] or row[0], row[2] or "")
            for row in cur.fetchall()
        }
        cur.close()
        print(f"[로드] VOD 시리즈 매핑: {len(vod_series_map):,}건")

        if args.vod_id:
            vod_ids = [args.vod_id]
        else:
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT vod_id_fk FROM vod_meta_embedding ORDER BY vod_id_fk"
            )
            vod_ids = [r[0] for r in cur.fetchall()]
            if args.limit:
                vod_ids = vod_ids[: args.limit]

        total = len(vod_ids)
        print(f"[시작] 대상 VOD {total:,}건  alpha={alpha}  top_n={top_n}")

        all_rows = []
        for i, vod_id in enumerate(vod_ids, 1):
            rows = process_vod(vod_id, conn, alpha, top_n,
                               vod_series_map=vod_series_map)
            all_rows.extend(rows)
            if i % 500 == 0 or i == total:
                print(f"  [{i}/{total}] 누적 {len(all_rows):,}건")

        df = pd.DataFrame(all_rows)
        df.to_parquet(out_file, index=False)
        print(f"\n[완료] {len(df):,}건 → {out_file}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
