"""
TMDB cast에서 cast_guest 보완

네이버에서 못 가져온 TV 연예/오락 시리즈 대상:
- TMDB search/tv → tv/{id}/credits에서 전체 cast 조회
- 앞 4명 = cast_lead, 5번째~ = cast_guest

실행: python Database_Design/scripts/fill_cast_guest_from_tmdb.py [--update]
"""

import io, sys, os, json, time, random
from urllib.request import urlopen, Request
from urllib.parse import urlencode

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.themoviedb.org/3"
API_KEY = os.getenv("TMDB_API_KEY")
CAST_LEAD_COUNT = 4


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
                time.sleep(1)
            else:
                print(f"  [WARN] API fail: {endpoint} -> {e}", file=sys.stderr)
                return None


def search_tv(query):
    """TMDB search/tv → KR origin 우선"""
    data = tmdb_get("search/tv", {"query": query})
    if not data or not data.get("results"):
        return None
    for r in data["results"]:
        if "KR" in r.get("origin_country", []):
            return r["id"]
    return data["results"][0]["id"]


def get_cast(tmdb_id):
    """TV credits에서 전체 cast 이름 리스트"""
    data = tmdb_get(f"tv/{tmdb_id}/credits")
    if not data:
        return []
    cast = data.get("cast", [])
    return [c["name"] for c in cast]


def main():
    do_update = "--update" in sys.argv
    if not do_update:
        print("=== DRY RUN (--update로 실행) ===\n")
    else:
        print("=== UPDATE 모드 ===\n")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # cast_guest가 없는 TV 연예/오락 시리즈
    cur.execute("""
        SELECT DISTINCT series_nm, COUNT(*) as ep_count
        FROM public.vod
        WHERE rag_source = 'TMDB_NEW_2025'
          AND ct_cl = 'TV 연예/오락'
          AND series_nm IS NOT NULL
          AND (cast_guest IS NULL OR cast_guest = '')
        GROUP BY series_nm
        ORDER BY series_nm
    """)
    series_list = cur.fetchall()
    print(f"대상: {len(series_list)}개 시리즈\n")

    updated = 0
    success = 0
    fail = 0
    results = []

    for idx, (series_nm, ep_count) in enumerate(series_list):
        tmdb_id = search_tv(series_nm)
        if not tmdb_id:
            fail += 1
            results.append((series_nm, ep_count, "TMDB_NOT_FOUND", []))
            time.sleep(0.05)
            continue

        cast = get_cast(tmdb_id)
        if len(cast) <= CAST_LEAD_COUNT:
            fail += 1
            results.append((series_nm, ep_count, f"CAST_{len(cast)}_ONLY", cast))
            time.sleep(0.05)
            continue

        lead_str = ", ".join(cast[:CAST_LEAD_COUNT])
        guest_str = ", ".join(cast[CAST_LEAD_COUNT:])

        if do_update:
            cur.execute("""
                UPDATE public.vod
                SET cast_lead = %s, cast_guest = %s
                WHERE series_nm = %s AND rag_source = 'TMDB_NEW_2025'
                  AND (cast_guest IS NULL OR cast_guest = '')
            """, (lead_str, guest_str, series_nm))
            updated += cur.rowcount
            conn.commit()

        success += 1
        results.append((series_nm, ep_count, f"OK({len(cast)}명)", cast))

        if (idx + 1) % 20 == 0:
            print(f"  진행: {idx+1}/{len(series_list)} (성공:{success}, 실패:{fail})")
        time.sleep(0.06)

    # 리포트
    print(f"\n{'=' * 70}")
    print(f"  대상: {len(series_list)}개 시리즈")
    print(f"  성공: {success}개, 실패: {fail}개")
    if do_update:
        print(f"  UPDATE: {updated}건")
    print(f"{'=' * 70}\n")

    print("--- 성공 ---")
    for nm, ep, status, cast in results:
        if status.startswith("OK"):
            lead = ", ".join(cast[:4])
            guest = ", ".join(cast[4:8])
            extra = f"... +{len(cast)-8}" if len(cast) > 8 else ""
            print(f"  {nm} ({ep}화) {status} lead:[{lead}] guest:[{guest}{extra}]")

    print(f"\n--- 실패 ({fail}개) ---")
    for nm, ep, status, cast in results:
        if not status.startswith("OK"):
            print(f"  {nm} ({ep}화) [{status}] {cast[:4] if cast else ''}")

    # 커버리지
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN cast_guest IS NOT NULL AND cast_guest != '' THEN 1 END) as has_guest,
            COUNT(CASE WHEN cast_lead IS NOT NULL AND cast_lead != '' THEN 1 END) as has_lead
        FROM public.vod
        WHERE rag_source = 'TMDB_NEW_2025' AND ct_cl = 'TV 연예/오락'
    """)
    total, has_guest, has_lead = cur.fetchone()
    print(f"\n--- 커버리지 (TV 연예/오락, {total}건) ---")
    print(f"  cast_lead:  {has_lead}/{total} ({has_lead/total*100:.1f}%)")
    print(f"  cast_guest: {has_guest}/{total} ({has_guest/total*100:.1f}%)")

    conn.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
