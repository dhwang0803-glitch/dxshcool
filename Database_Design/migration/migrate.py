"""
VOD 추천 시스템 - PostgreSQL 마이그레이션 스크립트
CSV 데이터 → PostgreSQL 3개 테이블 적재

사용법:
    python migrate.py  # .env 파일에서 연결 정보 자동 로드

적재 순서:
    1. user 테이블 (user_table.csv)
    2. vod 테이블 (vod_table.csv)
    3. watch_history 테이블 (watch_history_table.csv, 5,000건 배치 / 배치당 새 연결)
"""

import os
import math
import logging
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv
from pathlib import Path

# =============================================================
# 경로 및 설정
# =============================================================

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data" / "prepared_data"
LOG_FILE = Path(__file__).parent / "migration.log"
BATCH_SIZE = 5_000

# .env 파일 로드
load_dotenv(BASE_DIR / ".env")

# =============================================================
# 로깅 설정
# =============================================================

def setup_logging():
    logger = logging.getLogger("migrate")
    logger.setLevel(logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 파일 핸들러
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger


logger = setup_logging()

# =============================================================
# 데이터 변환 함수
# =============================================================

def parse_disp_rtm(disp_rtm_str) -> int:
    """
    "HH:MM" 또는 "HH:MM:SS" 형식을 초 단위 정수로 변환.
    None / NaN / "-" 는 0 반환.
    예: "01:21" -> 4860, "00:29" -> 1740, "01:30:00" -> 5400
    """
    if disp_rtm_str is None:
        return 0
    try:
        if math.isnan(float(disp_rtm_str)):
            return 0
    except (ValueError, TypeError):
        pass
    if str(disp_rtm_str).strip() == '-':
        return 0
    parts = str(disp_rtm_str).strip().split(':')
    try:
        if len(parts) == 2:
            h, m = int(parts[0]), int(parts[1])
            return h * 3600 + m * 60
        elif len(parts) == 3:
            h, m, s = int(parts[0]), int(parts[1]), int(parts[2])
            return h * 3600 + m * 60 + s
    except (ValueError, TypeError):
        logger.warning(f"disp_rtm 파싱 실패: {disp_rtm_str!r} → 0 저장")
        return 0
    return 0


def convert_nfx_use_yn(value) -> bool | None:
    """
    NFX_USE_YN 컬럼 변환:
    - "Y" -> True
    - "N" -> False
    - NaN / None -> None
    """
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (ValueError, TypeError):
        pass
    s = str(value).strip().upper()
    if s == 'Y':
        return True
    if s == 'N':
        return False
    return None


def clean_smry(value) -> str | None:
    """
    smry(줄거리) 컬럼 정제:
    - "-" -> None
    - "" (빈 문자열) -> None
    - NaN / None -> None
    - 정상 텍스트 -> 그대로 반환
    """
    if value is None:
        return None
    try:
        if math.isnan(float(value)):
            return None
    except (ValueError, TypeError):
        pass
    text = str(value).strip()
    if text == '-' or text == '':
        return None
    return text


def clip_completion_rate(value) -> float:
    """
    completion_rate 값을 0.0 ~ 1.0 범위로 클리핑.
    - 1.0 초과 -> 1.0
    - 0.0 미만 -> 0.0
    - 정상 범위 -> 그대로 반환
    """
    return max(0.0, min(1.0, float(value)))


# =============================================================
# DB 연결
# =============================================================

def get_connection():
    """환경변수에서 접속 정보를 읽어 psycopg2 연결 반환."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


# =============================================================
# USER 적재
# =============================================================

def load_users(conn):
    """USER 테이블 적재 (user_table.csv)."""
    csv_path = DATA_DIR / "user_table.csv"
    logger.info(f"USER 적재 시작: {csv_path}")

    df = pd.read_csv(csv_path)

    rename_map = {
        'AGE_GRP10': 'age_grp10',
        'INHOME_RATE': 'inhome_rate',
        'SVOD_SCRB_CNT_GRP': 'svod_scrb_cnt_grp',
        'PAID_CHNL_CNT_GRP': 'paid_chnl_cnt_grp',
        'CH_HH_AVG_MONTH1': 'ch_hh_avg_month1',
        'KIDS_USE_PV_MONTH1': 'kids_use_pv_month1',
    }
    df = df.rename(columns=rename_map)

    # NFX_USE_YN 변환
    df['nfx_use_yn'] = df['NFX_USE_YN'].apply(convert_nfx_use_yn)
    df = df.drop(columns=['NFX_USE_YN'], errors='ignore')

    cols = [
        'sha2_hash', 'age_grp10', 'inhome_rate',
        'svod_scrb_cnt_grp', 'paid_chnl_cnt_grp',
        'ch_hh_avg_month1', 'kids_use_pv_month1', 'nfx_use_yn',
    ]
    # 실제 존재하는 컬럼만 사용
    cols = [c for c in cols if c in df.columns]
    records = [tuple(row) for row in df[cols].itertuples(index=False, name=None)]

    col_str = ', '.join(cols)
    sql = f"""
        INSERT INTO "user" ({col_str})
        VALUES %s
        ON CONFLICT (sha2_hash) DO NOTHING
    """

    with conn.cursor() as cur:
        execute_values(cur, sql, records)
    conn.commit()
    logger.info(f"USER 적재 완료: {len(records):,}건")


# =============================================================
# VOD 적재
# =============================================================

def load_vods(conn):
    """VOD 테이블 적재 (vod_table.csv)."""
    csv_path = DATA_DIR / "vod_table.csv"
    logger.info(f"VOD 적재 시작: {csv_path}")

    df = pd.read_csv(csv_path)

    # disp_rtm_sec 변환
    df['disp_rtm_sec'] = df['disp_rtm'].apply(parse_disp_rtm)

    # smry 정제
    if 'smry' in df.columns:
        df['smry'] = df['smry'].apply(clean_smry)

    # CT_CL → ct_cl 소문자
    if 'CT_CL' in df.columns:
        df = df.rename(columns={'CT_CL': 'ct_cl'})

    cols = [
        'full_asset_id', 'asset_nm', 'ct_cl', 'disp_rtm', 'disp_rtm_sec',
        'genre', 'director', 'asset_prod', 'smry', 'provider',
        'genre_detail', 'series_nm',
    ]
    cols = [c for c in cols if c in df.columns]

    # None으로 교체 (NaN → None)
    df = df.where(pd.notnull(df), None)

    records = [tuple(row) for row in df[cols].itertuples(index=False, name=None)]

    col_str = ', '.join(cols)
    sql = f"""
        INSERT INTO vod ({col_str})
        VALUES %s
        ON CONFLICT (full_asset_id) DO NOTHING
    """

    with conn.cursor() as cur:
        execute_values(cur, sql, records)
    conn.commit()
    logger.info(f"VOD 적재 완료: {len(records):,}건")


# =============================================================
# WATCH_HISTORY 적재 (배치)
# =============================================================

def load_watch_history():
    """WATCH_HISTORY 테이블 배치 적재 (watch_history_table.csv, 배치마다 새 연결)."""
    csv_path = DATA_DIR / "watch_history_table.csv"
    logger.info(f"WATCH_HISTORY 적재 시작: {csv_path}")

    total_loaded = 0
    batch_no = 0

    for chunk in pd.read_csv(csv_path, chunksize=BATCH_SIZE):
        batch_no += 1

        # 컬럼 매핑
        chunk = chunk.rename(columns={
            'sha2_hash': 'user_id_fk',
            'full_asset_id': 'vod_id_fk',
        })

        # completion_rate 클리핑
        if 'completion_rate' in chunk.columns:
            chunk['completion_rate'] = chunk['completion_rate'].apply(
                lambda v: clip_completion_rate(v) if pd.notnull(v) else None
            )

        # strt_dt: TIMESTAMPTZ 파싱 (문자열 그대로 넘겨도 psycopg2가 처리)
        if 'strt_dt' in chunk.columns:
            chunk['strt_dt'] = pd.to_datetime(chunk['strt_dt'], errors='coerce')

        cols = ['user_id_fk', 'vod_id_fk', 'strt_dt', 'use_tms', 'completion_rate', 'satisfaction']
        cols = [c for c in cols if c in chunk.columns]

        chunk = chunk.where(pd.notnull(chunk), None)
        records = [tuple(row) for row in chunk[cols].itertuples(index=False, name=None)]

        col_str = ', '.join(cols)
        sql = f"""
            INSERT INTO watch_history ({col_str})
            VALUES %s
            ON CONFLICT (user_id_fk, vod_id_fk, strt_dt) DO NOTHING
        """

        # 배치마다 새 연결 생성 → VPC 장시간 연결 타임아웃 방지
        conn = get_connection()
        try:
            try:
                with conn.cursor() as cur:
                    execute_values(cur, sql, records)
                conn.commit()
                total_loaded += len(records)
                logger.info(
                    f"WATCH_HISTORY 배치 {batch_no} 완료: {len(records):,}건 "
                    f"(누계 {total_loaded:,}건)"
                )
            except psycopg2.errors.ForeignKeyViolation as e:
                conn.rollback()
                logger.warning(
                    f"배치 {batch_no} FK 위반 발생 → 건별 재시도 후 스킵: {e}"
                )
                _insert_batch_skip_fk(conn, sql, col_str, records)
        finally:
            conn.close()

    logger.info(f"WATCH_HISTORY 적재 완료: 총 {total_loaded:,}건")


def _insert_batch_skip_fk(conn, sql, col_str, records):
    """FK 위반 레코드를 건별로 처리하여 스킵."""
    skipped = 0
    for record in records:
        try:
            with conn.cursor() as cur:
                execute_values(cur, sql, [record])
            conn.commit()
        except psycopg2.errors.ForeignKeyViolation:
            conn.rollback()
            skipped += 1
            logger.warning(f"FK 위반 스킵: {record}")
    if skipped:
        logger.warning(f"FK 위반으로 스킵된 레코드: {skipped:,}건")


# =============================================================
# 마이그레이션 후 검증
# =============================================================

def validate_counts(conn):
    """마이그레이션 후 데이터 건수 확인."""
    sql = """
        SELECT
            (SELECT COUNT(*) FROM "user")         AS user_count,
            (SELECT COUNT(*) FROM vod)             AS vod_count,
            (SELECT COUNT(*) FROM watch_history)   AS watch_count
    """
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    logger.info(
        f"[검증] user={row[0]:,}건, vod={row[1]:,}건, watch_history={row[2]:,}건"
    )
    logger.info("기대값: user=242,702 / vod=166,159 / watch_history=3,992,530")


# =============================================================
# 메인
# =============================================================

def main():
    logger.info("=" * 60)
    logger.info("VOD 추천 시스템 마이그레이션 시작")
    logger.info("=" * 60)

    conn = get_connection()
    try:
        load_users(conn)
        load_vods(conn)
    except Exception as e:
        conn.rollback()
        logger.error(f"마이그레이션 중 오류 발생: {e}", exc_info=True)
        raise
    finally:
        conn.close()

    # watch_history는 배치마다 독립 연결 사용 (VPC 타임아웃 방지)
    load_watch_history()

    conn = get_connection()
    try:
        validate_counts(conn)
        logger.info("마이그레이션 완료")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
