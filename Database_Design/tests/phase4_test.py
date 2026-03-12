"""
Phase 4 확장 테이블 테스트
vod_embedding(pgvector) + vod_recommendation 검증

실행:
    python Database_Design/tests/phase4_test.py
"""

import sys
import time
import psycopg2
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent.parent
RESULTS = []


# ── 유틸 ──────────────────────────────────────────────────────────────────────

def load_env():
    for candidate in [PROJECT_ROOT / ".env", PROJECT_ROOT / "Database_Design" / ".env"]:
        if candidate.exists():
            env = {}
            with open(candidate, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        env[k.strip()] = v.strip()
            return env
    raise FileNotFoundError(".env 없음")


def get_conn():
    env = load_env()
    return psycopg2.connect(
        host=env['DB_HOST'], port=int(env['DB_PORT']),
        dbname=env['DB_NAME'], user=env['DB_USER'], password=env['DB_PASSWORD'],
        connect_timeout=10,
    )


def record(test_id, name, passed, actual, target=None, note=""):
    status = "PASS" if passed else "FAIL"
    RESULTS.append({
        "id": test_id, "name": name, "status": status,
        "actual": actual, "target": target, "note": note,
    })
    tgt = f" (목표: {target})" if target else ""
    print(f"  [{status}] {test_id} {name}: {actual}{tgt}" + (f" — {note}" if note else ""))


def elapsed_ms(start):
    return round((time.perf_counter() - start) * 1000, 1)


# ── 테스트 ────────────────────────────────────────────────────────────────────

def test_e01_schema(conn):
    """E01: vod_embedding 스키마 검증"""
    print("\n[E01] vod_embedding 스키마 검증")
    cur = conn.cursor()

    # 컬럼 존재 확인
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'vod_embedding'
    """)
    cols = {r[0] for r in cur.fetchall()}
    required = {'vod_embedding_id', 'vod_id_fk', 'embedding',
                'embedding_type', 'model_version', 'vector_magnitude',
                'frame_count', 'source_type', 'created_at', 'updated_at'}
    missing = required - cols
    record("E01-1", "필수 컬럼 존재", not missing,
           f"누락={missing or '없음'}", "필수 컬럼 전체 존재")

    # UNIQUE 제약 확인
    cur.execute("""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'vod_embedding'::regclass AND contype = 'u'
    """)
    constraints = {r[0]: r[1] for r in cur.fetchall()}
    uq_ok = any('vod_id_fk' in v and 'model_name' not in v
                for v in constraints.values())
    record("E01-2", "UNIQUE(vod_id_fk) 단독 제약", uq_ok,
           str(constraints), "vod_id_fk 단독 UNIQUE")

    # CHECK 제약 확인
    cur.execute("""
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'vod_embedding'::regclass AND contype = 'c'
    """)
    checks = {r[0] for r in cur.fetchall()}
    record("E01-3", "CHECK 제약 존재",
           'chk_embedding_type' in checks and 'chk_source_type' in checks,
           str(checks), "chk_embedding_type, chk_source_type")

    # 인덱스 확인
    cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = 'vod_embedding'")
    indexes = {r[0] for r in cur.fetchall()}
    record("E01-4", "보조 인덱스 존재",
           'idx_vod_emb_type' in indexes and 'idx_vod_emb_updated' in indexes,
           str(indexes))


def test_e02_data_integrity(conn):
    """E02: 파일럿 데이터 무결성"""
    print("\n[E02] 파일럿 데이터 무결성")
    cur = conn.cursor()

    # 적재 건수
    cur.execute("SELECT COUNT(*) FROM vod_embedding")
    cnt = cur.fetchone()[0]
    record("E02-1", "적재 건수", cnt >= 78, f"{cnt}건", ">=78건 (파일럿)")

    # FK 무결성: vod_id_fk 가 vod 테이블에 존재하는지
    cur.execute("""
        SELECT COUNT(*) FROM vod_embedding ve
        LEFT JOIN vod v ON ve.vod_id_fk = v.full_asset_id
        WHERE v.full_asset_id IS NULL
    """)
    orphan = cur.fetchone()[0]
    record("E02-2", "FK 무결성 (vod 참조)", orphan == 0,
           f"고아 레코드 {orphan}건", "0건")

    # 이상 벡터 (magnitude 범위 벗어남)
    cur.execute("""
        SELECT COUNT(*) FROM vod_embedding
        WHERE vector_magnitude < 0.01 OR vector_magnitude > 100
    """)
    anomaly = cur.fetchone()[0]
    record("E02-3", "이상 벡터", anomaly == 0, f"{anomaly}건", "0건")

    # NULL 벡터
    cur.execute("SELECT COUNT(*) FROM vod_embedding WHERE embedding IS NULL")
    null_vec = cur.fetchone()[0]
    record("E02-4", "NULL 벡터", null_vec == 0, f"{null_vec}건", "0건")

    # embedding_type 분포
    cur.execute("""
        SELECT embedding_type, COUNT(*) FROM vod_embedding GROUP BY 1
    """)
    dist = {r[0]: r[1] for r in cur.fetchall()}
    record("E02-5", "embedding_type 분포", True, str(dist))


def test_e03_vector_search(conn):
    """E03: 코사인 유사도 검색 응답 시간"""
    print("\n[E03] 코사인 유사도 검색")
    cur = conn.cursor()

    # 기준 벡터 하나 가져오기
    cur.execute("SELECT vod_id_fk, embedding FROM vod_embedding LIMIT 1")
    row = cur.fetchone()
    if not row:
        record("E03-1", "유사도 검색 (LIMIT 10)", False, "데이터 없음")
        return
    target_vod_id, target_emb = row

    # Cold 실행
    start = time.perf_counter()
    cur.execute("""
        SELECT ve.vod_id_fk, v.asset_nm,
               1 - (ve.embedding <=> %s::vector) AS similarity
        FROM vod_embedding ve
        JOIN vod v ON ve.vod_id_fk = v.full_asset_id
        WHERE ve.vod_id_fk != %s
        ORDER BY ve.embedding <=> %s::vector
        LIMIT 10
    """, (target_emb, target_vod_id, target_emb))
    rows = cur.fetchall()
    cold_ms = elapsed_ms(start)
    record("E03-1", "유사도 검색 cold (LIMIT 10)",
           cold_ms < 1000, f"{cold_ms}ms", "<1000ms")

    # Warm 실행
    start = time.perf_counter()
    cur.execute("""
        SELECT ve.vod_id_fk, v.asset_nm,
               1 - (ve.embedding <=> %s::vector) AS similarity
        FROM vod_embedding ve
        JOIN vod v ON ve.vod_id_fk = v.full_asset_id
        WHERE ve.vod_id_fk != %s
        ORDER BY ve.embedding <=> %s::vector
        LIMIT 10
    """, (target_emb, target_vod_id, target_emb))
    rows = cur.fetchall()
    warm_ms = elapsed_ms(start)
    record("E03-2", "유사도 검색 warm (LIMIT 10)",
           warm_ms < 500, f"{warm_ms}ms", "<500ms")

    print(f"     기준 VOD: {target_vod_id}")
    print(f"     상위 3개 유사 VOD:")
    for vod_id, asset_nm, sim in rows[:3]:
        print(f"       {asset_nm[:30]:30s}  similarity={sim:.4f}")


def test_e04_vod_recommendation(conn):
    """E04: vod_recommendation 테이블 생성 및 CRUD"""
    print("\n[E04] vod_recommendation 테이블")
    cur = conn.cursor()

    # 테이블 존재 확인 또는 생성
    cur.execute("SELECT to_regclass('public.vod_recommendation')")
    exists = cur.fetchone()[0]

    if not exists:
        print("     테이블 없음 — create_embedding_tables.sql 기준으로 생성 중...")
        cur.execute("""
            CREATE TABLE vod_recommendation (
                recommendation_id   BIGINT          GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id_fk          VARCHAR(64)     NOT NULL,
                vod_id_fk           VARCHAR(64)     NOT NULL,
                rank                SMALLINT        NOT NULL,
                score               REAL            NOT NULL,
                recommendation_type VARCHAR(32)     NOT NULL DEFAULT 'VISUAL_SIMILARITY',
                generated_at        TIMESTAMPTZ     DEFAULT NOW(),
                expires_at          TIMESTAMPTZ     DEFAULT NOW() + INTERVAL '7 days',
                CONSTRAINT fk_vod_rec_user
                    FOREIGN KEY (user_id_fk) REFERENCES "user"(sha2_hash) ON DELETE CASCADE,
                CONSTRAINT fk_vod_rec_vod
                    FOREIGN KEY (vod_id_fk) REFERENCES vod(full_asset_id) ON DELETE CASCADE,
                CONSTRAINT uq_vod_rec_user_vod UNIQUE (user_id_fk, vod_id_fk),
                CONSTRAINT chk_rec_score CHECK (score >= 0 AND score <= 1),
                CONSTRAINT chk_rec_rank  CHECK (rank >= 1),
                CONSTRAINT chk_rec_type  CHECK (recommendation_type IN
                    ('VISUAL_SIMILARITY', 'COLLABORATIVE', 'HYBRID'))
            )
        """)
        cur.execute("CREATE INDEX idx_vod_rec_user    ON vod_recommendation (user_id_fk, rank)")
        cur.execute("CREATE INDEX idx_vod_rec_expires ON vod_recommendation (expires_at)")
        conn.commit()
        record("E04-1", "vod_recommendation 테이블 생성", True, "CREATE 성공")
    else:
        record("E04-1", "vod_recommendation 테이블 존재", True, "기존 테이블")

    # 테스트용 user / vod 조회
    cur.execute('SELECT sha2_hash FROM "user" LIMIT 1')
    user_row = cur.fetchone()
    cur.execute("SELECT vod_id_fk FROM vod_embedding LIMIT 1")
    vod_row = cur.fetchone()

    if not user_row or not vod_row:
        record("E04-2", "INSERT 테스트", False, "user 또는 vod 데이터 없음")
        return

    test_user = user_row[0]
    test_vod  = vod_row[0]

    # INSERT
    cur.execute("""
        INSERT INTO vod_recommendation (user_id_fk, vod_id_fk, rank, score, recommendation_type)
        VALUES (%s, %s, 1, 0.95, 'VISUAL_SIMILARITY')
        ON CONFLICT (user_id_fk, vod_id_fk) DO UPDATE
            SET score = EXCLUDED.score, rank = EXCLUDED.rank,
                generated_at = NOW(), expires_at = NOW() + INTERVAL '7 days'
        RETURNING recommendation_id
    """, (test_user, test_vod))
    rec_id = cur.fetchone()[0]
    conn.commit()
    record("E04-2", "INSERT / ON CONFLICT UPDATE", rec_id is not None,
           f"recommendation_id={rec_id}")

    # expires_at 자동 설정 확인
    cur.execute("""
        SELECT expires_at > NOW(), expires_at < NOW() + INTERVAL '8 days'
        FROM vod_recommendation WHERE recommendation_id = %s
    """, (rec_id,))
    ttl_row = cur.fetchone()
    record("E04-3", "TTL expires_at (7일)",
           ttl_row and all(ttl_row), str(ttl_row), "(True, True)")

    # TTL 만료 삭제 쿼리 검증 (만료된 건 없으므로 0건 삭제 확인)
    cur.execute("""
        DELETE FROM vod_recommendation
        WHERE expires_at < NOW()
        RETURNING recommendation_id
    """)
    deleted = cur.rowcount
    conn.commit()
    record("E04-4", "TTL 만료 삭제 쿼리", deleted == 0,
           f"삭제 {deleted}건", "0건 (방금 삽입한 건은 만료 안됨)")

    # 정리
    cur.execute("DELETE FROM vod_recommendation WHERE recommendation_id = %s", (rec_id,))
    conn.commit()


def test_e05_conflict_and_check(conn):
    """E05: CHECK 제약 위반 및 ON CONFLICT 동작"""
    print("\n[E05] CHECK 제약 및 UNIQUE 충돌")
    cur = conn.cursor()

    # CHECK 위반: embedding_type 잘못된 값
    try:
        cur.execute("""
            UPDATE vod_embedding SET embedding_type = 'INVALID'
            WHERE vod_embedding_id = (SELECT vod_embedding_id FROM vod_embedding LIMIT 1)
        """)
        conn.rollback()
        record("E05-1", "CHECK embedding_type 위반 차단", False, "제약 미동작")
    except psycopg2.errors.CheckViolation:
        conn.rollback()
        record("E05-1", "CHECK embedding_type 위반 차단", True, "CheckViolation 발생")

    # ON CONFLICT: 동일 vod_id_fk 재삽입 시 UPDATE
    cur.execute("SELECT vod_id_fk, vector_magnitude FROM vod_embedding LIMIT 1")
    row = cur.fetchone()
    if row:
        vod_id, old_mag = row
        cur.execute("""
            INSERT INTO vod_embedding (vod_id_fk, embedding, embedding_type,
                embedding_dim, model_version, vector_magnitude, frame_count, source_type)
            SELECT vod_id_fk, embedding, embedding_type, embedding_dim,
                   model_version, 99.0, frame_count, source_type
            FROM vod_embedding WHERE vod_id_fk = %s
            ON CONFLICT (vod_id_fk) DO UPDATE
                SET vector_magnitude = EXCLUDED.vector_magnitude
            RETURNING vector_magnitude
        """, (vod_id,))
        new_mag = cur.fetchone()[0]
        conn.commit()
        updated = abs(new_mag - 99.0) < 0.01
        record("E05-2", "ON CONFLICT DO UPDATE 동작", updated,
               f"magnitude {old_mag:.4f} → {new_mag:.4f}", "99.0으로 업데이트")

        # 원복
        cur.execute("""
            UPDATE vod_embedding SET vector_magnitude = %s WHERE vod_id_fk = %s
        """, (old_mag, vod_id))
        conn.commit()


# ── 리포트 출력 ───────────────────────────────────────────────────────────────

def print_summary():
    total  = len(RESULTS)
    passed = sum(1 for r in RESULTS if r['status'] == 'PASS')
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"Phase 4 테스트 결과: {passed}/{total} PASS  ({failed} FAIL)")
    print("=" * 60)
    if failed:
        print("FAIL 항목:")
        for r in RESULTS:
            if r['status'] == 'FAIL':
                print(f"  {r['id']} {r['name']}: {r['actual']}")
    return passed, total


def save_report(passed, total):
    report_path = PROJECT_ROOT / "Database_Design" / "reports" / "phase4_report.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        "# Phase 4 테스트 결과\n",
        f"**실행일**: {now}  \n",
        f"**환경**: VPC PostgreSQL 15.4 + pgvector 0.5.1  \n",
        f"**결과**: {passed}/{total} PASS\n",
        "\n---\n",
        "\n## 테스트 항목별 결과\n",
        "\n| ID | 테스트 항목 | 판정 | 실제값 | 목표 |",
        "|-----|-----------|------|--------|------|",
    ]
    for r in RESULTS:
        tgt = r['target'] or "-"
        lines.append(f"| {r['id']} | {r['name']} | **{r['status']}** | {r['actual']} | {tgt} |")

    lines += ["\n\n---\n", f"\n**전체**: {passed}/{total} PASS\n"]
    report_path.write_text("\n".join(lines), encoding='utf-8')
    print(f"\n리포트 저장: {report_path}")


# ── 메인 ──────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("Phase 4 확장 테이블 테스트 시작")
    print("=" * 60)

    conn = get_conn()
    try:
        test_e01_schema(conn)
        test_e02_data_integrity(conn)
        test_e03_vector_search(conn)
        test_e04_vod_recommendation(conn)
        test_e05_conflict_and_check(conn)
    finally:
        conn.close()

    passed, total = print_summary()
    save_report(passed, total)


if __name__ == "__main__":
    main()
