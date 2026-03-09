"""
PLAN_00b Step 1: DB에서 cast_lead 결측 VOD 100건 층화추출 (ct_cl 비율 유지)
출력: RAG/data/comparison_sample.csv
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

import os
import csv
import math
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

OUTPUT = ROOT / "RAG" / "data" / "comparison_sample.csv"


def extract_sample(n: int = 100) -> list[dict]:
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        dbname=os.getenv("DB_NAME"),
        connect_timeout=10,
    )
    cur = conn.cursor()

    # 1단계: ct_cl별 비율 파악
    cur.execute("""
        SELECT ct_cl, COUNT(*) AS cnt
        FROM vod
        WHERE cast_lead IS NULL
          AND asset_nm IS NOT NULL AND asset_nm != ''
        GROUP BY ct_cl
        ORDER BY cnt DESC;
    """)
    dist = cur.fetchall()
    total_pool = sum(r[1] for r in dist)

    # 2단계: ct_cl별 할당 건수 계산 (비율 유지, 최소 1건)
    quotas = {}
    allocated = 0
    for ct_cl, cnt in dist:
        q = max(1, round(n * cnt / total_pool))
        quotas[ct_cl] = q
        allocated += q

    # 반올림 오차 조정 (가장 큰 그룹에서 보정)
    diff = allocated - n
    largest_cl = dist[0][0]
    quotas[largest_cl] = max(1, quotas[largest_cl] - diff)

    # 3단계: ct_cl별 RANDOM 추출 후 합산
    rows = []
    for ct_cl, quota in quotas.items():
        cur.execute("""
            SELECT full_asset_id, asset_nm, ct_cl, genre
            FROM vod
            WHERE cast_lead IS NULL
              AND asset_nm IS NOT NULL AND asset_nm != ''
              AND ct_cl = %s
            ORDER BY RANDOM()
            LIMIT %s;
        """, (ct_cl, quota))
        for r in cur.fetchall():
            rows.append({
                "full_asset_id": r[0],
                "asset_nm": r[1],
                "ct_cl": r[2] or "",
                "genre": r[3] or "",
            })

    conn.close()
    return rows


def save_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["full_asset_id", "asset_nm", "ct_cl", "genre"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    print("DB에서 샘플 추출 중...")
    rows = extract_sample(100)
    save_csv(rows, OUTPUT)
    print(f"완료: {len(rows)}건 → {OUTPUT}")

    # ct_cl 분포 출력
    from collections import Counter
    dist = Counter(r["ct_cl"] for r in rows)
    for cl, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {cl or '(없음)':20s}: {cnt}건")
