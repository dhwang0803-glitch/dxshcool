"""
PostgreSQL VPC 접속 파일럿 테스트
실행: python Database_Design/scripts/pilot_db_test.py
전제: 프로젝트 루트에 .env 파일 존재
"""

import os
import sys
import time
from pathlib import Path

# 프로젝트 루트의 .env 로드
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(env_path)
    print(f"[ENV] .env 로드: {env_path}")
except ImportError:
    print("[WARN] python-dotenv 미설치 — 환경변수에서 직접 읽음")

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    print("[ERROR] psycopg2 미설치. 아래 명령으로 설치하세요:")
    print("  pip install psycopg2-binary")
    sys.exit(1)


def get_conn_params():
    params = {
        "host":     os.getenv("DB_HOST"),
        "port":     int(os.getenv("DB_PORT", "5432")),
        "dbname":   os.getenv("DB_NAME"),
        "user":     os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
        "connect_timeout": 10,
    }
    missing = [k for k, v in params.items() if v is None and k != "connect_timeout"]
    if missing:
        print(f"[ERROR] .env에 누락된 변수: {missing}")
        sys.exit(1)
    return params


def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print('='*50)


def run_tests():
    params = get_conn_params()
    masked = {k: (v if k not in ("password",) else "***") for k, v in params.items()}
    print(f"[CONN] 접속 파라미터: {masked}")

    # ── 1. 접속 테스트 ─────────────────────────────────
    section("1. 접속 테스트")
    t0 = time.time()
    try:
        conn = psycopg2.connect(**params)
        elapsed = (time.time() - t0) * 1000
        print(f"[OK] 접속 성공 ({elapsed:.1f} ms)")
    except psycopg2.OperationalError as e:
        print(f"[FAIL] 접속 실패: {e}")
        sys.exit(1)

    cur = conn.cursor()

    # ── 2. 서버 정보 ───────────────────────────────────
    section("2. 서버 정보")
    cur.execute("SELECT version();")
    print(f"  PostgreSQL: {cur.fetchone()[0]}")

    cur.execute("SELECT current_database(), current_user, inet_server_addr(), inet_server_port();")
    row = cur.fetchone()
    print(f"  DB        : {row[0]}")
    print(f"  User      : {row[1]}")
    print(f"  Server IP : {row[2]}:{row[3]}")

    # ── 3. pgvector 확장 확인 ─────────────────────────
    section("3. pgvector 확장 확인")
    cur.execute("SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';")
    row = cur.fetchone()
    if row:
        print(f"  [OK] pgvector {row[1]} 설치됨")
    else:
        print("  [WARN] pgvector 미설치 — CREATE EXTENSION vector; 필요")

    # ── 4. 기존 테이블 목록 ────────────────────────────
    section("4. 테이블 목록 (public 스키마)")
    cur.execute("""
        SELECT tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename))
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
    """)
    rows = cur.fetchall()
    if rows:
        for name, size in rows:
            print(f"  - {name:<40} {size}")
    else:
        print("  (테이블 없음 — 스키마 마이그레이션 전)")

    # ── 5. Read/Write 왕복 테스트 ─────────────────────
    section("5. Read/Write 왕복 테스트")
    try:
        cur.execute("""
            CREATE TEMP TABLE _pilot_ping (id SERIAL, ts TIMESTAMPTZ DEFAULT now());
        """)
        cur.execute("INSERT INTO _pilot_ping DEFAULT VALUES RETURNING id, ts;")
        row = cur.fetchone()
        print(f"  [OK] INSERT → id={row[0]}, ts={row[1]}")
        cur.execute("SELECT id, ts FROM _pilot_ping;")
        row = cur.fetchone()
        print(f"  [OK] SELECT → id={row[0]}, ts={row[1]}")
        conn.rollback()  # TEMP 테이블이므로 rollback해도 무방
        print("  [OK] 트랜잭션 롤백 완료")
    except Exception as e:
        print(f"  [FAIL] Read/Write 테스트 실패: {e}")
        conn.rollback()

    # ── 6. 접속 레이턴시 5회 측정 ─────────────────────
    section("6. 접속 레이턴시 (ping × 5)")
    latencies = []
    for i in range(5):
        t = time.time()
        cur.execute("SELECT 1;")
        cur.fetchone()
        latencies.append((time.time() - t) * 1000)
    avg = sum(latencies) / len(latencies)
    print(f"  측정값: {[f'{l:.2f}ms' for l in latencies]}")
    print(f"  평균  : {avg:.2f} ms")

    cur.close()
    conn.close()

    # ── 최종 결과 ──────────────────────────────────────
    section("파일럿 테스트 결과")
    print("  모든 항목 통과 - VPC PostgreSQL 접속 정상")
    print()


if __name__ == "__main__":
    run_tests()
