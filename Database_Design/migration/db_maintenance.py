"""
VOD 추천 시스템 - DB 자정 유지보수 스크립트
==============================================
실행 시간: 매일 자정 00:00 (OS cron으로 스케줄링)
실행 방법:
    python db_maintenance.py

OS cron 등록 방법 (VPC Linux):
    $ crontab -e
    0 0 * * * /usr/bin/python3 /path/to/Database_Design/migration/db_maintenance.py >> /path/to/maintenance.log 2>&1

매일 수행:
    1. MV 4개 REFRESH CONCURRENTLY (읽기 락 없음, 운영 중 실행 가능)
       - mv_vod_satisfaction_stats  (P04: 만족도 상위 VOD)
       - mv_age_grp_vod_stats       (P06: 연령대별 선호 VOD)
       - mv_vod_watch_stats         (P02: VOD별 시청 통계 / 대시보드 배너)
       - mv_daily_watch_stats       (P03: 일별 시청 통계)

매주 일요일 추가 수행:
    2. 다음 주 파티션 자동 생성 (2주 선행 생성으로 여유 확보)
       - 파티션명: watch_history_YYYYMMDD (해당 주 일요일 기준)
       - 인덱스 5개 자동 생성
       - DEFAULT 파티션 잔류 데이터 확인 (이상 징후 감지)

의존 패키지:
    pip install psycopg2-binary python-dotenv
"""

import os
import logging
from datetime import date, timedelta
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# =============================================================
# 경로 및 설정
# =============================================================

BASE_DIR   = Path(__file__).parent.parent
LOG_FILE   = Path(__file__).parent / "maintenance.log"
ENV_FILE   = BASE_DIR / ".env"

# REFRESH CONCURRENTLY 최대 허용 시간 (초) — 전체 MV가 이 시간 안에 끝나야 함
MV_TIMEOUT_SEC = 3600  # 1시간

# 파티션 선행 생성 주 수 (2 = 오늘 포함 2주 후까지 보장)
PARTITION_LOOKAHEAD_WEEKS = 2

# =============================================================
# 로깅 설정
# =============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("db_maintenance")


# =============================================================
# DB 연결
# =============================================================

def get_connection() -> psycopg2.extensions.connection:
    load_dotenv(ENV_FILE)
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=30,
    )


# =============================================================
# MV REFRESH
# =============================================================

# REFRESH 순서: 의존성 없는 MV는 순서 무관. 가벼운 MV 먼저.
MATERIALIZED_VIEWS = [
    "mv_daily_watch_stats",        # P03: 일별 집계 (경량)
    "mv_age_grp_vod_stats",        # P06: 연령대별 집계
    "mv_vod_watch_stats",          # P02: VOD별 전체 통계
    "mv_vod_satisfaction_stats",   # P04: 만족도 상위 VOD (최중량)
]


def refresh_materialized_views(conn: psycopg2.extensions.connection) -> bool:
    """
    MV 4개를 CONCURRENTLY REFRESH.
    CONCURRENTLY: 기존 데이터 유지하며 갱신 → 조회 중단 없음.
    단, 각 MV에 UNIQUE INDEX 존재해야 함 (없으면 일반 REFRESH로 폴백).
    """
    log.info("── MV REFRESH 시작 ──")
    all_ok = True

    for mv_name in MATERIALIZED_VIEWS:
        try:
            # CONCURRENTLY는 autocommit 모드에서만 실행 가능
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = '{MV_TIMEOUT_SEC}s'")
                log.info(f"  REFRESH 시작: {mv_name}")
                cur.execute(
                    f"REFRESH MATERIALIZED VIEW CONCURRENTLY {mv_name}"
                )
            log.info(f"  REFRESH 완료: {mv_name}")
        except psycopg2.errors.ObjectNotInPrerequisiteState as e:
            # UNIQUE INDEX 없을 때 — 일반 REFRESH로 폴백 (락 발생 주의)
            log.warning(
                f"  CONCURRENTLY 불가 ({mv_name}), 일반 REFRESH 시도: {e}"
            )
            try:
                with conn.cursor() as cur:
                    cur.execute(f"REFRESH MATERIALIZED VIEW {mv_name}")
            except Exception as e2:
                log.error(f"  REFRESH 실패: {mv_name} — {e2}")
                all_ok = False
        except psycopg2.errors.UndefinedTable:
            log.warning(f"  MV 없음 (미생성 상태): {mv_name} — 건너뜀")
        except Exception as e:
            log.error(f"  REFRESH 실패: {mv_name} — {e}")
            all_ok = False
        finally:
            conn.autocommit = False

    log.info("── MV REFRESH 완료 ──")
    return all_ok


# =============================================================
# 주별 파티션 자동 생성
# =============================================================

def _week_start(target_date: date) -> date:
    """
    target_date가 속하는 주의 일요일(주 시작일)을 반환.
    파티션 경계: 매주 일요일 00:00:00 UTC 기준 (7일 단위).
    """
    # weekday(): Mon=0 ... Sun=6 → 일요일 기준 정렬
    days_since_sunday = (target_date.weekday() + 1) % 7
    return target_date - timedelta(days=days_since_sunday)


def _partition_name(week_start_date: date) -> str:
    """파티션 테이블명: watch_history_YYYYMMDD (해당 주 일요일)"""
    return f"watch_history_{week_start_date.strftime('%Y%m%d')}"


def _partition_exists(cur, partition_name: str) -> bool:
    cur.execute(
        "SELECT 1 FROM pg_class WHERE relname = %s AND relkind = 'r'",
        (partition_name,),
    )
    return cur.fetchone() is not None


def _create_partition(cur, week_start_date: date) -> str:
    """
    주별 파티션 + 인덱스 생성.
    인덱스는 파티션 테이블에 직접 생성 (부모 인덱스 자동 전파 방식과 동일).
    반환: 생성된 파티션 이름
    """
    week_end_date = week_start_date + timedelta(days=7)
    partition_name = _partition_name(week_start_date)
    start_str = week_start_date.isoformat()
    end_str = week_end_date.isoformat()

    # 파티션 생성
    cur.execute(f"""
        CREATE TABLE {partition_name}
            PARTITION OF watch_history
            FOR VALUES FROM ('{start_str} 00:00:00+00')
                        TO   ('{end_str} 00:00:00+00')
    """)
    log.info(f"  파티션 생성: {partition_name} [{start_str} ~ {end_str})")

    # 인덱스 생성 (파티션 내 로컬 인덱스)
    indexes = [
        (f"idx_{partition_name}_user_id",
         f"CREATE INDEX idx_{partition_name}_user_id ON {partition_name} (user_id_fk)"),

        (f"idx_{partition_name}_vod_id",
         f"CREATE INDEX idx_{partition_name}_vod_id ON {partition_name} (vod_id_fk)"),

        (f"idx_{partition_name}_strt_dt",
         f"CREATE INDEX idx_{partition_name}_strt_dt ON {partition_name} (strt_dt)"),

        (f"idx_{partition_name}_user_covering",
         f"""CREATE INDEX idx_{partition_name}_user_covering
             ON {partition_name} (user_id_fk, strt_dt DESC)
             INCLUDE (vod_id_fk, completion_rate, satisfaction)"""),

        (f"idx_{partition_name}_satisfaction",
         f"""CREATE INDEX idx_{partition_name}_satisfaction
             ON {partition_name} (satisfaction DESC)
             WHERE satisfaction > 0"""),
    ]

    for idx_name, idx_sql in indexes:
        cur.execute(idx_sql)
        log.info(f"    인덱스 생성: {idx_name}")

    return partition_name


def ensure_partitions(conn: psycopg2.extensions.connection) -> None:
    """
    오늘부터 PARTITION_LOOKAHEAD_WEEKS 주 앞까지 파티션이 존재하는지 확인하고,
    없으면 생성.
    매주 일요일에 실행되지만, 매일 실행해도 idempotent (존재하면 건너뜀).
    """
    log.info("── 파티션 자동 생성 확인 ──")
    today = date.today()

    weeks_to_check = [
        _week_start(today + timedelta(weeks=i))
        for i in range(PARTITION_LOOKAHEAD_WEEKS + 1)
    ]

    created = 0
    conn.autocommit = False

    for week_start_date in weeks_to_check:
        partition_name = _partition_name(week_start_date)
        try:
            with conn.cursor() as cur:
                if _partition_exists(cur, partition_name):
                    log.info(f"  이미 존재: {partition_name} — 건너뜀")
                    continue
                _create_partition(cur, week_start_date)
            conn.commit()
            created += 1
        except Exception as e:
            conn.rollback()
            log.error(f"  파티션 생성 실패: {partition_name} — {e}")

    if created == 0:
        log.info("  신규 생성 파티션 없음 (모두 이미 존재)")
    else:
        log.info(f"  총 {created}개 파티션 생성 완료")

    log.info("── 파티션 확인 완료 ──")


def check_default_partition(conn: psycopg2.extensions.connection) -> None:
    """
    DEFAULT 파티션에 잔류 데이터가 있으면 경고 로그 출력.
    파티션 생성 누락이나 예상 외 날짜 데이터 유입의 이상 징후.
    """
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM watch_history_default")
            count = cur.fetchone()[0]

        if count > 0:
            log.warning(
                f"[경고] DEFAULT 파티션에 {count:,}건 잔류 — "
                "파티션 범위 외 데이터 또는 파티션 생성 누락 가능성. 수동 확인 필요."
            )
        else:
            log.info("  DEFAULT 파티션 잔류 데이터: 없음 (정상)")
    except psycopg2.errors.UndefinedTable:
        log.info("  DEFAULT 파티션 없음 (partition_watch_history.sql 미실행 상태)")
    except Exception as e:
        log.warning(f"  DEFAULT 파티션 확인 실패: {e}")


# =============================================================
# 메인
# =============================================================

def main() -> None:
    log.info("=" * 60)
    log.info(f"DB 자정 유지보수 시작: {date.today()}")
    log.info("=" * 60)

    conn = get_connection()
    try:
        # ── 1. MV REFRESH (매일) ──────────────────────────────
        mv_ok = refresh_materialized_views(conn)
        if not mv_ok:
            log.warning("일부 MV REFRESH 실패. 로그 확인 필요.")

        # ── 2. 파티션 자동 생성 (매일 확인, 없으면 생성) ──────
        ensure_partitions(conn)

        # ── 3. DEFAULT 파티션 이상 징후 확인 ──────────────────
        check_default_partition(conn)

    except Exception as e:
        log.error(f"유지보수 중 예외 발생: {e}", exc_info=True)
        raise
    finally:
        conn.close()

    log.info("=" * 60)
    log.info("DB 자정 유지보수 완료")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
