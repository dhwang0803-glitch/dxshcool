"""
2023년 2월 watch_history 정제 → 로컬 parquet 저장

추천 엔진 오프라인 평가를 위한 테스트 데이터:
- 학습: 1월 watch_history (DB)
- 평가: 2월 watch_history (이 스크립트 → parquet)

DB에 적재하지 않음 — CF_Engine/Vector_Search 학습 데이터 오염 방지.
평가 스크립트가 parquet에서 직접 읽어 추천 결과와 비교.

사용법:
    python scripts/test_data_upload.py                          # 실행
    python scripts/test_data_upload.py --chunk-size 50000       # 청크 크기 조정
    python scripts/test_data_upload.py --csv /path/to/file.csv  # CSV 경로 지정
    python scripts/test_data_upload.py --output /path/to/out.parquet  # 출력 경로 지정
"""
import argparse
import os
import sys
from pathlib import Path

import pandas as pd
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DEFAULT_CSV = r"C:\Users\user\myworkspace\proj_2nd\자료\202302_VOD.csv"
DEFAULT_OUTPUT = str(Path(__file__).parent.parent / "data" / "202302_watch_history.parquet")
BAYESIAN_M = 5.0
MIN_WATCH_SEC = 60


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def disp_rtm_to_sec(rtm: str) -> float | None:
    """'HH:MM' 또는 'HH:MM:SS' → 초 변환."""
    if not isinstance(rtm, str) or not rtm.strip():
        return None
    parts = rtm.strip().split(":")
    try:
        if len(parts) == 2:
            return int(parts[0]) * 3600 + int(parts[1]) * 60
        elif len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None
    return None


def load_db_sets(conn) -> tuple[set[str], set[str]]:
    """DB에 존재하는 user sha2_hash, vod full_asset_id 집합 로드."""
    cur = conn.cursor()

    print("[DB] 유저 목록 로드...", end=" ", flush=True)
    cur.execute('SELECT sha2_hash FROM public."user"')
    user_set = {row[0] for row in cur.fetchall()}
    print(f"{len(user_set):,}명")

    print("[DB] VOD 목록 로드...", end=" ", flush=True)
    cur.execute("SELECT full_asset_id FROM public.vod")
    vod_set = {row[0] for row in cur.fetchall()}
    print(f"{len(vod_set):,}건")

    cur.close()
    return user_set, vod_set


def process_to_parquet(
    csv_path: str,
    conn,
    user_set: set[str],
    vod_set: set[str],
    chunk_size: int,
    output_path: str,
):
    """CSV를 청크 단위로 읽어 정제 → parquet 저장."""

    # ── 1차 패스: VOD별 시청 건수 + 전체 평균 completion_rate 집계 ──
    print("\n[1차 패스] VOD별 시청 건수 & 전체 평균 완주율 집계...")
    vod_counts: dict[str, int] = {}
    total_cr = 0.0
    total_cr_count = 0
    total_rows_raw = 0
    total_filtered = 0

    for chunk in pd.read_csv(csv_path, chunksize=chunk_size, dtype=str):
        total_rows_raw += len(chunk)

        # 기본 필터: DB에 있는 유저 + VOD만
        mask = chunk["sha2_hash"].isin(user_set) & chunk["asset"].isin(vod_set)
        filtered = chunk[mask]
        total_filtered += len(filtered)

        # 벡터화 처리 (iterrows 대신)
        vod_series = filtered["asset"]
        for vod_id in vod_series:
            vod_counts[vod_id] = vod_counts.get(vod_id, 0) + 1

        rtm_secs = filtered["disp_rtm"].apply(disp_rtm_to_sec)
        use_tms_vals = pd.to_numeric(filtered["use_tms"], errors="coerce").fillna(0)
        valid = (rtm_secs.notna()) & (rtm_secs > 0) & (use_tms_vals > MIN_WATCH_SEC)
        if valid.any():
            crs = (use_tms_vals[valid] / rtm_secs[valid]).clip(upper=1.0)
            total_cr += crs.sum()
            total_cr_count += len(crs)

        if total_rows_raw % 500000 < chunk_size:
            print(f"  [{total_rows_raw:,}행] 필터 통과: {total_filtered:,}건")

    global_avg_cr = total_cr / total_cr_count if total_cr_count > 0 else 0.5
    print(f"\n[1차 패스 완료]")
    print(f"  원본: {total_rows_raw:,}행")
    print(f"  필터 통과: {total_filtered:,}건")
    print(f"  유효 VOD 종류: {len(vod_counts):,}건")
    print(f"  전체 평균 완주율 (C): {global_avg_cr:.4f}")

    if total_filtered == 0:
        print("[ERROR] 필터 통과 데이터 없음. 유저/VOD 매칭 확인 필요.")
        return

    # ── 2차 패스: 정제 → parquet 저장 ──
    print(f"\n[2차 패스] 정제 → parquet 저장...")

    result_chunks: list[pd.DataFrame] = []
    processed = 0
    skipped = 0

    for chunk in pd.read_csv(csv_path, chunksize=chunk_size, dtype=str):
        mask = chunk["sha2_hash"].isin(user_set) & chunk["asset"].isin(vod_set)
        filtered = chunk[mask].copy()

        if filtered.empty:
            continue

        # strt_dt 변환
        filtered["strt_dt_str"] = filtered["strt_dt"].astype(str).str.strip()
        valid_strt = filtered["strt_dt_str"].str.len() >= 14
        skipped += (~valid_strt).sum()
        filtered = filtered[valid_strt].copy()

        if filtered.empty:
            continue

        filtered["strt_dt_parsed"] = pd.to_datetime(
            filtered["strt_dt_str"], format="%Y%m%d%H%M%S", errors="coerce"
        )
        bad_dt = filtered["strt_dt_parsed"].isna()
        skipped += bad_dt.sum()
        filtered = filtered[~bad_dt].copy()

        if filtered.empty:
            continue

        # use_tms
        filtered["use_tms_float"] = pd.to_numeric(filtered["use_tms"], errors="coerce").fillna(0)

        # completion_rate
        filtered["rtm_sec"] = filtered["disp_rtm"].apply(disp_rtm_to_sec)
        has_rtm = filtered["rtm_sec"].notna() & (filtered["rtm_sec"] > 0)
        filtered["completion_rate"] = None
        filtered.loc[has_rtm, "completion_rate"] = (
            (filtered.loc[has_rtm, "use_tms_float"] / filtered.loc[has_rtm, "rtm_sec"])
            .clip(upper=1.0)
            .round(4)
        )

        # satisfaction (베이지안 스코어)
        filtered["v"] = filtered["asset"].map(vod_counts).fillna(1).astype(int)
        cr_vals = filtered["completion_rate"].astype(float)

        low_watch = (filtered["use_tms_float"] <= MIN_WATCH_SEC) | filtered["completion_rate"].isna()
        filtered["satisfaction"] = 0.0
        valid_sat = ~low_watch
        if valid_sat.any():
            v = filtered.loc[valid_sat, "v"]
            r = cr_vals[valid_sat]
            filtered.loc[valid_sat, "satisfaction"] = (
                (v * r + BAYESIAN_M * global_avg_cr) / (v + BAYESIAN_M)
            ).round(4)

        # 결과 컬럼 선택
        out = pd.DataFrame({
            "user_id_fk": filtered["sha2_hash"],
            "vod_id_fk": filtered["asset"],
            "strt_dt": filtered["strt_dt_parsed"],
            "use_tms": filtered["use_tms_float"],
            "completion_rate": filtered["completion_rate"].astype(float),
            "satisfaction": filtered["satisfaction"].astype(float),
        })
        result_chunks.append(out)
        processed += len(out)

        if processed % 500000 < chunk_size:
            print(f"  [{processed:,}건 처리]")

    if not result_chunks:
        print("[ERROR] 정제 결과 0건")
        return

    # parquet 저장
    print(f"\n[저장] parquet 병합 중...")
    result_df = pd.concat(result_chunks, ignore_index=True)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    result_df.to_parquet(output_path, index=False)

    print(f"\n[완료]")
    print(f"  정제: {len(result_df):,}건")
    print(f"  스킵: {skipped:,}건")
    print(f"  저장: {output_path}")
    print(f"\n  유저 수: {result_df['user_id_fk'].nunique():,}명")
    print(f"  VOD 수: {result_df['vod_id_fk'].nunique():,}건")


def main():
    parser = argparse.ArgumentParser(
        description="2월 watch_history 정제 → parquet (DB 적재 X, 평가 전용)"
    )
    parser.add_argument("--csv", default=DEFAULT_CSV, help="202302_VOD.csv 경로")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="출력 parquet 경로")
    parser.add_argument("--chunk-size", type=int, default=50000, help="청크 크기 (기본 50000)")
    args = parser.parse_args()

    if not os.path.exists(args.csv):
        print(f"[ERROR] CSV 파일 없음: {args.csv}")
        sys.exit(1)

    print("=" * 60)
    print("2월 watch_history 정제 → parquet (평가 전용)")
    print(f"  CSV: {args.csv}")
    print(f"  출력: {args.output}")
    print(f"  chunk_size: {args.chunk_size:,}")
    print(f"  베이지안 m: {BAYESIAN_M}, 최소 시청: {MIN_WATCH_SEC}초")
    print("  ※ DB 적재 없음 — 학습 데이터 오염 방지")
    print("=" * 60)

    conn = get_connection()
    try:
        user_set, vod_set = load_db_sets(conn)
    finally:
        conn.close()

    process_to_parquet(
        csv_path=args.csv,
        conn=None,
        user_set=user_set,
        vod_set=vod_set,
        chunk_size=args.chunk_size,
        output_path=args.output,
    )

    print("\n" + "=" * 60)
    print("[다음 단계]")
    print("  평가 스크립트에서 이 parquet을 로드하여:")
    print("  - DB의 추천 결과 (serving.vod_recommendation) vs 2월 실제 시청")
    print("  - Precision@K, Recall@K, NDCG 산출")
    print("=" * 60)


if __name__ == "__main__":
    main()
