"""실패분 CSV 추출 / 수동 편집 후 results.parquet 머지.

1) 추출: results.parquet에서 누락된 (vod_id, segment_id) 쌍을 CSV로 내보냄
   python gen_rec_sentence/scripts/edit_failed.py extract \
       gen_rec_sentence/data/colab_data

2) 머지: 수동 편집한 CSV를 results.parquet에 합침
   python gen_rec_sentence/scripts/edit_failed.py merge \
       gen_rec_sentence/data/colab_data \
       gen_rec_sentence/data/colab_data/failed_edit.csv
"""

import argparse
import logging
import os
import sys

import pandas as pd

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_N_SEGMENTS = 5


def extract(offline_dir: str) -> None:
    ctx_path = os.path.join(offline_dir, "vod_contexts.parquet")
    result_path = os.path.join(offline_dir, "results.parquet")
    out_csv = os.path.join(offline_dir, "failed_edit.csv")

    df_ctx = pd.read_parquet(ctx_path)
    log.info("VOD 컨텍스트: %d건", len(df_ctx))

    # 전체 대상 쌍
    all_pairs = {(row["vod_id"], seg) for _, row in df_ctx.iterrows() for seg in range(_N_SEGMENTS)}

    # 기존 성공 쌍
    existing = set()
    if os.path.exists(result_path):
        df_res = pd.read_parquet(result_path)
        existing = {(r["vod_id"], int(r["segment_id"])) for _, r in df_res.iterrows()}
        # no-filter로 생성했지만 아직 results에 들어간 것도 포함
        # rec_sentence가 있는 것만 성공으로 침
        if "rec_sentence" in df_res.columns:
            has_sentence = df_res.dropna(subset=["rec_sentence"])
            existing = {(r["vod_id"], int(r["segment_id"])) for _, r in has_sentence.iterrows()}
    log.info("기존 성공: %d건", len(existing))

    missing = sorted(all_pairs - existing)
    log.info("누락(실패) 쌍: %d건", len(missing))

    if not missing:
        log.info("누락 없음. 종료.")
        return

    # CSV 작성: vod_id, segment_id, asset_nm, genre_detail, rec_sentence(빈칸)
    ctx_map = {row["vod_id"]: row for _, row in df_ctx.iterrows()}
    rows = []
    for vod_id, seg_id in missing:
        ctx = ctx_map.get(vod_id, {})
        rows.append({
            "vod_id": vod_id,
            "segment_id": seg_id,
            "asset_nm": ctx.get("asset_nm", ""),
            "genre_detail": ctx.get("genre_detail", ""),
            "rec_sentence": "",  # 수동 입력
        })

    df_out = pd.DataFrame(rows)
    df_out.to_csv(out_csv, index=False, encoding="utf-8-sig")
    log.info("CSV 저장: %s (%d건)", out_csv, len(rows))
    log.info("rec_sentence 컬럼을 채운 후 merge 명령으로 합치세요.")


def merge(offline_dir: str, csv_path: str, model_name: str = "manual_edit") -> None:
    result_path = os.path.join(offline_dir, "results.parquet")

    df_edit = pd.read_csv(csv_path, encoding="utf-8-sig")
    # rec_sentence가 비어있는 행 제거
    df_edit = df_edit.dropna(subset=["rec_sentence"])
    df_edit = df_edit[df_edit["rec_sentence"].str.strip() != ""]
    log.info("편집 CSV 로드: %d건 (빈 행 제외)", len(df_edit))

    if df_edit.empty:
        log.warning("편집된 문장이 없습니다.")
        return

    # 기존 results 로드
    if os.path.exists(result_path):
        df_res = pd.read_parquet(result_path)
    else:
        df_res = pd.DataFrame(columns=["vod_id", "segment_id", "rec_sentence", "model_name"])

    # 편집분을 results 형식으로 변환
    new_rows = []
    for _, row in df_edit.iterrows():
        new_rows.append({
            "vod_id": row["vod_id"],
            "segment_id": int(row["segment_id"]),
            "rec_sentence": row["rec_sentence"].strip(),
            "model_name": model_name,
        })
    df_new = pd.DataFrame(new_rows)

    # 기존 results에서 편집분과 겹치는 키 제거 후 합침
    merge_keys = set(zip(df_new["vod_id"], df_new["segment_id"]))
    df_res_filtered = df_res[
        ~df_res.apply(lambda r: (r["vod_id"], int(r["segment_id"])) in merge_keys, axis=1)
    ]

    df_merged = pd.concat([df_res_filtered, df_new], ignore_index=True)
    df_merged.to_parquet(result_path, index=False)
    log.info("머지 완료: %s (%d건, +%d건 편집분)", result_path, len(df_merged), len(df_new))


def main():
    parser = argparse.ArgumentParser(description="실패분 CSV 추출/머지")
    sub = parser.add_subparsers(dest="cmd")

    p_ext = sub.add_parser("extract", help="누락 쌍을 CSV로 추출")
    p_ext.add_argument("offline_dir", help="colab_data 디렉토리")

    p_mrg = sub.add_parser("merge", help="편집 CSV를 results.parquet에 머지")
    p_mrg.add_argument("offline_dir", help="colab_data 디렉토리")
    p_mrg.add_argument("csv_path", help="편집한 CSV 경로")
    p_mrg.add_argument("--model-name", default="manual_edit", help="model_name 값 (default: manual_edit)")

    args = parser.parse_args()
    if args.cmd == "extract":
        extract(args.offline_dir)
    elif args.cmd == "merge":
        merge(args.offline_dir, args.csv_path, args.model_name)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
