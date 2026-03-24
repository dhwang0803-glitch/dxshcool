"""
TMDB 평점 일괄 수집 → vod.tmdb_vote_average/tmdb_vote_count/tmdb_popularity

병렬 처리 (ThreadPoolExecutor, 20 workers)로 TMDB API 호출 속도 향상.

전략:
  1) series_nm 기준 DISTINCT 목록 → TMDB search/tv or search/movie
  2) search 결과에 vote_average, vote_count, popularity 포함 → detail 호출 불필요
  3) 병렬 API 호출 → 결과 수집 → 일괄 UPDATE
  4) series_nm IS NULL인 단독 VOD → asset_nm으로 검색

실행: python Database_Design/scripts/fill_tmdb_ratings.py [--update]
"""

import io, sys, os, json, time
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.themoviedb.org/3"
API_KEY = os.getenv("TMDB_API_KEY")
WORKERS = 20


def tmdb_get(endpoint, params=None):
    p = dict(params or {})
    p["api_key"] = API_KEY
    p["language"] = "ko-KR"
    url = f"{BASE}/{endpoint}?{urlencode(p)}"
    for attempt in range(3):
        try:
            with urlopen(Request(url), timeout=20) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt < 2:
                time.sleep(0.5)
            else:
                return None


def search_and_extract(query, media_type="tv"):
    """TMDB search → vote_average, vote_count, popularity 추출"""
    data = tmdb_get(f"search/{media_type}", {"query": query})
    if not data or not data.get("results"):
        return None

    if media_type == "tv":
        for r in data["results"]:
            if "KR" in r.get("origin_country", []):
                return {
                    "vote_average": r.get("vote_average", 0),
                    "vote_count": r.get("vote_count", 0),
                    "popularity": r.get("popularity", 0),
                }

    r = data["results"][0]
    return {
        "vote_average": r.get("vote_average", 0),
        "vote_count": r.get("vote_count", 0),
        "popularity": r.get("popularity", 0),
    }


def fetch_one_series(args):
    """워커 함수: (series_nm, ct_cl) → (series_nm, result_dict or None)"""
    series_nm, ct_cl = args
    media_type = "movie" if ct_cl == "영화" else "tv"
    result = search_and_extract(series_nm, media_type)
    if not result and media_type == "tv":
        result = search_and_extract(series_nm, "movie")
    return (series_nm, result)


def fetch_one_standalone(args):
    """워커 함수: (asset_id, asset_nm, ct_cl) → (asset_id, result_dict or None)"""
    asset_id, asset_nm, ct_cl = args
    media_type = "movie" if ct_cl == "영화" else "tv"
    result = search_and_extract(asset_nm, media_type)
    if not result and media_type == "tv":
        result = search_and_extract(asset_nm, "movie")
    return (asset_id, result)


def main():
    do_update = "--update" in sys.argv
    mode = "UPDATE" if do_update else "DRY RUN"
    print(f"=== {mode} 모드 (workers={WORKERS}) ===\n")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # 1) 미수집 시리즈 목록
    cur.execute("""
        SELECT series_nm,
               (array_agg(DISTINCT ct_cl))[1] as ct_cl
        FROM public.vod
        WHERE tmdb_vote_average IS NULL
          AND series_nm IS NOT NULL
        GROUP BY series_nm
    """)
    series_list = [(r[0], r[1]) for r in cur.fetchall()]

    # 2) 단독 VOD
    cur.execute("""
        SELECT full_asset_id, asset_nm, ct_cl
        FROM public.vod
        WHERE tmdb_vote_average IS NULL
          AND series_nm IS NULL
    """)
    standalone_list = cur.fetchall()

    print(f"미수집 시리즈: {len(series_list):,}개, 단독: {len(standalone_list):,}개\n")

    # --- 시리즈 병렬 수집 ---
    print(f"[1/2] 시리즈 TMDB 수집 (병렬 {WORKERS} workers)...")
    t0 = time.time()
    success = 0
    fail = 0
    updated_rows = 0
    batch_updates = []

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch_one_series, item): item for item in series_list}
        for i, future in enumerate(as_completed(futures)):
            series_nm, result = future.result()
            if result:
                success += 1
                batch_updates.append((result["vote_average"], result["vote_count"],
                                      result["popularity"], series_nm))
            else:
                fail += 1

            # 500건마다 DB flush
            if len(batch_updates) >= 500:
                if do_update:
                    for params in batch_updates:
                        cur.execute("""
                            UPDATE public.vod
                            SET tmdb_vote_average = %s, tmdb_vote_count = %s, tmdb_popularity = %s
                            WHERE series_nm = %s AND tmdb_vote_average IS NULL
                        """, params)
                    updated_rows += sum(1 for _ in batch_updates)  # approx
                    conn.commit()
                batch_updates.clear()

            done = i + 1
            if done % 1000 == 0:
                elapsed = time.time() - t0
                rate = done / elapsed
                eta = (len(series_list) - done) / rate
                print(f"  {done:,}/{len(series_list):,} "
                      f"(성공:{success:,} 실패:{fail:,}) "
                      f"{rate:.0f}/s ETA {eta:.0f}s")

    # 남은 batch flush
    if batch_updates and do_update:
        for params in batch_updates:
            cur.execute("""
                UPDATE public.vod
                SET tmdb_vote_average = %s, tmdb_vote_count = %s, tmdb_popularity = %s
                WHERE series_nm = %s AND tmdb_vote_average IS NULL
            """, params)
        conn.commit()
    batch_updates.clear()

    elapsed = time.time() - t0
    print(f"\n  시리즈 완료: {elapsed:.0f}초, 성공 {success:,}, 실패 {fail:,}")

    # --- 단독 VOD 병렬 수집 ---
    if standalone_list:
        print(f"\n[2/2] 단독 VOD TMDB 수집 ({len(standalone_list)}건)...")
        t1 = time.time()
        st_success = 0
        st_fail = 0

        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = {pool.submit(fetch_one_standalone, item): item for item in standalone_list}
            for future in as_completed(futures):
                asset_id, result = future.result()
                if result:
                    st_success += 1
                    if do_update:
                        cur.execute("""
                            UPDATE public.vod
                            SET tmdb_vote_average = %s, tmdb_vote_count = %s, tmdb_popularity = %s
                            WHERE full_asset_id = %s AND tmdb_vote_average IS NULL
                        """, (result["vote_average"], result["vote_count"],
                              result["popularity"], asset_id))
                else:
                    st_fail += 1

        if do_update:
            conn.commit()
        print(f"  단독 완료: {time.time()-t1:.0f}초, 성공 {st_success}, 실패 {st_fail}")
    else:
        st_success = st_fail = 0

    # --- 리포트 ---
    total_targets = len(series_list) + len(standalone_list)
    total_success = success + st_success
    total_fail = fail + st_fail

    print(f"\n{'=' * 60}")
    print(f"  총 대상: {total_targets:,}")
    print(f"  성공: {total_success:,} ({total_success/max(total_targets,1)*100:.1f}%)")
    print(f"  실패: {total_fail:,}")
    print(f"  소요: {time.time()-t0:.0f}초")
    print(f"{'=' * 60}")

    # 커버리지
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(tmdb_vote_average) as has_va
        FROM public.vod
    """)
    total, has_va = cur.fetchone()
    print(f"\n--- 커버리지 ({total:,}건) ---")
    print(f"  tmdb_vote_average: {has_va:,}/{total:,} ({has_va/total*100:.1f}%)")

    conn.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
