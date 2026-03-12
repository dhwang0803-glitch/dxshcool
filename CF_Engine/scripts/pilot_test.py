"""
CF_Engine 파일럿 테스트
- ALS 학습 속도 측정
- poster_url 커버리지 확인 (추천된 VOD 중 포스터 있는 비율)

실행: python scripts/pilot_test.py
"""

import sys
import time
from pathlib import Path

import numpy as np
import psycopg2
from scipy.sparse import csr_matrix
import implicit

sys.stdout.reconfigure(encoding='utf-8')


def get_conn():
    env_path = Path(__file__).parent.parent.parent / '.env'
    env = {}
    for line in env_path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()
    return psycopg2.connect(
        host=env.get('DB_HOST'), port=env.get('DB_PORT'),
        user=env.get('DB_USER'), password=env.get('DB_PASSWORD'),
        dbname=env.get('DB_NAME')
    )


def load_data(conn, sample_users=5000):
    print(f"\n[STEP 1] watch_history 로드 (샘플 유저 {sample_users:,}명)")
    t0 = time.time()
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*), COUNT(DISTINCT user_id_fk), COUNT(DISTINCT vod_id_fk)
        FROM watch_history
    """)
    total_rows, total_users, total_items = cur.fetchone()
    print(f"  전체 규모: {total_rows:,}행 / {total_users:,}유저 / {total_items:,}아이템")

    cur.execute(f"""
        WITH sampled AS (
            SELECT user_id_fk FROM watch_history
            GROUP BY user_id_fk ORDER BY random() LIMIT {sample_users}
        )
        SELECT w.user_id_fk, w.vod_id_fk, w.completion_rate
        FROM watch_history w
        JOIN sampled s ON w.user_id_fk = s.user_id_fk
        WHERE w.completion_rate IS NOT NULL
    """)
    rows = cur.fetchall()
    cur.close()

    print(f"  샘플 로드: {len(rows):,}행 ({time.time()-t0:.1f}초)")
    return rows, total_users, total_items


def build_matrix(rows, alpha=40):
    print(f"\n[STEP 2] User-Item 희소 행렬 구성 (alpha={alpha})")
    t0 = time.time()

    user_enc = {u: i for i, u in enumerate(sorted(set(r[0] for r in rows)))}
    item_enc = {v: i for i, v in enumerate(sorted(set(r[1] for r in rows)))}

    users = [user_enc[r[0]] for r in rows]
    items = [item_enc[r[1]] for r in rows]
    confs = [1.0 + alpha * float(r[2]) for r in rows]

    mat = csr_matrix((confs, (users, items)), shape=(len(user_enc), len(item_enc)))
    sparsity = 1 - mat.nnz / (mat.shape[0] * mat.shape[1])

    print(f"  행렬: {mat.shape[0]:,} x {mat.shape[1]:,}  |  희소성: {sparsity*100:.2f}%  |  {time.time()-t0:.2f}초")
    return mat, user_enc, item_enc


def train_als(mat, factors=64, iterations=10):
    print(f"\n[STEP 3] ALS 학습 (factors={factors}, iterations={iterations})")
    t0 = time.time()

    model = implicit.als.AlternatingLeastSquares(
        factors=factors, iterations=iterations,
        regularization=0.01, use_gpu=False,
    )
    model.fit(mat.T.tocsr())

    elapsed = time.time() - t0
    print(f"  학습 완료: {elapsed:.1f}초  |  속도: {mat.shape[0]*iterations/elapsed:.0f} user-iter/초")
    return model, elapsed


def generate_recommendations(model, mat, item_enc, top_k=20, sample_n=100):
    print(f"\n[STEP 4] 추천 생성 (Top-{top_k}, 샘플 {sample_n}명)")
    t0 = time.time()

    item_dec = {v: k for k, v in item_enc.items()}
    rec_vod_ids = set()
    for uid in range(min(sample_n, mat.shape[0])):
        ids, _ = model.recommend(uid, mat, N=top_k, filter_already_liked_items=True)
        rec_vod_ids.update(item_dec[i] for i in ids)

    elapsed = time.time() - t0
    print(f"  추천 완료: {min(sample_n, mat.shape[0])/elapsed:.0f}명/초  |  고유 추천 VOD: {len(rec_vod_ids):,}건")
    return list(rec_vod_ids)


def check_poster_coverage(conn, rec_vod_ids):
    print(f"\n[STEP 5] poster_url 커버리지")
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*), COUNT(poster_url),
               ROUND(COUNT(poster_url)*100.0/COUNT(*), 1)
        FROM vod
    """)
    total, has_poster, pct_all = cur.fetchone()
    print(f"  전체 VOD:  {total:,}건 중 {has_poster:,}건 ({pct_all}%) poster_url 보유")

    pct_rec = None
    if rec_vod_ids:
        placeholders = ','.join(['%s'] * len(rec_vod_ids))
        cur.execute(f"""
            SELECT COUNT(*), COUNT(poster_url),
                   ROUND(COUNT(poster_url)*100.0/NULLIF(COUNT(*),0), 1)
            FROM vod WHERE full_asset_id IN ({placeholders})
        """, rec_vod_ids)
        r_total, r_poster, pct_rec = cur.fetchone()
        print(f"  추천 VOD:  {r_total:,}건 중 {r_poster:,}건 ({pct_rec}%) poster_url 보유")

    cur.close()
    return pct_all, pct_rec


def main():
    print("=" * 55)
    print("  CF_Engine 파일럿 테스트")
    print("=" * 55)
    t_total = time.time()

    conn = get_conn()
    print("  DB 접속 완료")

    rows, total_users, total_items = load_data(conn, sample_users=5000)
    mat, user_enc, item_enc = build_matrix(rows)
    model, train_sec = train_als(mat, factors=64, iterations=10)
    rec_vod_ids = generate_recommendations(model, mat, item_enc, top_k=20, sample_n=100)
    check_poster_coverage(conn, rec_vod_ids)
    conn.close()

    # 전체 데이터 학습 시간 추정 (factors=128, iter=20)
    scale = (total_users / mat.shape[0]) * (128 / 64) * (20 / 10)
    print(f"\n{'='*55}")
    print(f"  총 소요: {time.time()-t_total:.1f}초")
    print(f"  전체 데이터 학습 시간 추정 (factors=128, iter=20): ~{train_sec*scale/60:.1f}분")
    print("=" * 55)


if __name__ == "__main__":
    main()
