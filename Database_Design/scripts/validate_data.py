"""
VOD 추천 시스템 - 마이그레이션 전 CSV 사전 검사 스크립트
PLAN_02_DATA_MIGRATION.md 섹션 3 기준

사용법:
    python validate_data.py
"""

import sys
import pandas as pd
from pathlib import Path

# =============================================================
# 경로 설정
# =============================================================

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "prepared_data"

USER_CSV  = DATA_DIR / "user_table.csv"
VOD_CSV   = DATA_DIR / "vod_table.csv"
WH_CSV    = DATA_DIR / "watch_history_table.csv"

# =============================================================
# 출력 헬퍼
# =============================================================

def pass_msg(msg: str):
    print(f"[PASS] {msg}")

def warn_msg(msg: str):
    print(f"[WARNING] {msg}")

def fail_msg(msg: str):
    print(f"[FAIL] {msg}")

# =============================================================
# 검사 로직
# =============================================================

def validate():
    print("=== 데이터 검증 결과 ===")
    has_error = False

    # ── 1. CSV 로드 ────────────────────────────────────────────
    try:
        user_df = pd.read_csv(USER_CSV)
    except FileNotFoundError:
        fail_msg(f"USER CSV 파일 없음: {USER_CSV}")
        has_error = True
        user_df = None

    try:
        vod_df = pd.read_csv(VOD_CSV)
    except FileNotFoundError:
        fail_msg(f"VOD CSV 파일 없음: {VOD_CSV}")
        has_error = True
        vod_df = None

    try:
        wh_df = pd.read_csv(WH_CSV)
    except FileNotFoundError:
        fail_msg(f"WATCH_HISTORY CSV 파일 없음: {WH_CSV}")
        has_error = True
        wh_df = None

    # ── 2. USER 중복 sha2_hash 확인 ────────────────────────────
    if user_df is not None:
        total_user = len(user_df)
        unique_user = user_df['sha2_hash'].nunique()
        dup_user = total_user - unique_user
        if dup_user == 0:
            pass_msg(f"USER 중복 없음 ({total_user:,}건)")
        else:
            warn_msg(f"USER 중복 sha2_hash {dup_user:,}건 존재 (전체 {total_user:,}건)")
            has_error = True

    # ── 3. VOD 중복 full_asset_id 확인 ─────────────────────────
    if vod_df is not None:
        total_vod = len(vod_df)
        unique_vod = vod_df['full_asset_id'].nunique()
        dup_vod = total_vod - unique_vod
        if dup_vod == 0:
            pass_msg(f"VOD 중복 없음 ({total_vod:,}건)")
        else:
            warn_msg(f"VOD 중복 full_asset_id {dup_vod:,}건 존재 (전체 {total_vod:,}건)")
            has_error = True

    # ── 4. FK 무결성 확인 ──────────────────────────────────────
    if user_df is not None and vod_df is not None and wh_df is not None:
        user_ids = set(user_df['sha2_hash'].unique())
        vod_ids  = set(vod_df['full_asset_id'].unique())

        wh_user_ids = set(wh_df['sha2_hash'].unique())
        wh_vod_ids  = set(wh_df['full_asset_id'].unique())

        orphan_users = wh_user_ids - user_ids
        orphan_vods  = wh_vod_ids  - vod_ids

        if len(orphan_users) == 0 and len(orphan_vods) == 0:
            pass_msg("FK 무결성 통과")
        else:
            if len(orphan_users) > 0:
                warn_msg(
                    f"WATCH_HISTORY → USER FK 불일치: orphan sha2_hash {len(orphan_users):,}건"
                )
            if len(orphan_vods) > 0:
                warn_msg(
                    f"WATCH_HISTORY → VOD FK 불일치: orphan full_asset_id {len(orphan_vods):,}건"
                )
            has_error = True

    # ── 5. completion_rate 범위 확인 (0~2 허용, 2 초과 경고) ───
    if wh_df is not None and 'completion_rate' in wh_df.columns:
        cr = wh_df['completion_rate'].dropna()
        over_one  = int((cr > 1.0).sum())
        over_two  = int((cr > 2.0).sum())
        under_zero = int((cr < 0.0).sum())

        if over_two > 0:
            warn_msg(
                f"completion_rate 2.0 초과 {over_two:,}건 → 수동 확인 필요"
            )
        if over_one > 0:
            warn_msg(
                f"completion_rate 범위 초과 {over_one:,}건 → 클리핑 예정"
            )
        else:
            pass_msg("completion_rate 범위 정상 (0~1)")

        if under_zero > 0:
            warn_msg(f"completion_rate 음수 {under_zero:,}건 → 클리핑 예정")

    # ── 6. NULL 현황 출력 ──────────────────────────────────────
    print("\n=== NULL 현황 ===")
    if vod_df is not None:
        for col in ['director', 'smry']:
            if col in vod_df.columns:
                null_cnt = int(vod_df[col].isnull().sum())
                print(f"{col}: {null_cnt:,}건")
            else:
                print(f"{col}: 컬럼 없음")

    # ── 7. 데이터 건수 요약 ────────────────────────────────────
    print("\n=== 데이터 건수 요약 ===")
    if user_df is not None:
        print(f"USER         : {len(user_df):>12,}건  (기대값: 242,702건)")
    if vod_df is not None:
        print(f"VOD          : {len(vod_df):>12,}건  (기대값: 166,159건)")
    if wh_df is not None:
        print(f"WATCH_HISTORY: {len(wh_df):>12,}건  (기대값: 3,992,530건)")

    print("\n=== 검증 완료 ===")
    if has_error:
        print("일부 경고 또는 오류가 있습니다. 위 내용을 확인하세요.")
        sys.exit(1)
    else:
        print("모든 검증 통과. 마이그레이션을 진행할 수 있습니다.")


# =============================================================
# 메인
# =============================================================

if __name__ == "__main__":
    validate()
