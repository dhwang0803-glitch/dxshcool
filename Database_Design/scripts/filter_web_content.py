"""
TMDB networks 기반 방송사 분류 → 웹드라마/웹예능 제거

1) DB에서 TMDB_NEW_2025 TV 시리즈 목록(series_nm 기준) 조회
2) TMDB Search API로 series_nm → tmdb_id 매핑
3) TMDB TV detail의 networks 필드에서 방송사 추출
4) 주요 방송사 목록에 없는 시리즈 → DB에서 DELETE

주요 방송사: KBS, MBC, SBS, EBS, JTBC, tvN, OCN, Mnet 등 (CJ ENM 계열 포함)

실행: python Database_Design/scripts/filter_web_content.py [--dry-run] [--delete]
"""

import io, sys, os, json, time, re
from urllib.request import urlopen, Request
from urllib.parse import urlencode, quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

BASE = "https://api.themoviedb.org/3"
API_KEY = os.getenv("TMDB_API_KEY")

# ─── 주요 방송사 (정규화) ───
MAJOR_NETWORKS = {
    # 지상파
    "KBS", "KBS1", "KBS2", "KBS 1TV", "KBS 2TV", "KBS Drama Special",
    "MBC", "MBC every1", "MBC M", "MBC ON",
    "SBS", "SBS Plus", "SBS FiL",
    "EBS", "EBS 1TV", "EBS 2TV", "EBS 1", "EBS 2",
    # 종편
    "JTBC", "JTBC2", "JTBC4",
    "TV CHOSUN", "TV Chosun",
    "MBN",
    "Channel A",
    # CJ ENM 계열
    "CJ ENM",
    "tvN", "OCN", "Mnet", "XtvN", "O'live", "tooniverse",
    "tvN STORY", "tvN SHOW",
    # 기타 주요 케이블
    "WAVVE", "Tving", "Coupang Play",
    "Disney+", "Netflix",
    "KT Seezn", "Seezn",
    "Amazon Prime Video",
    "Apple TV+",
    "Viki",
    # 기타 유명 채널
    "Channel CGV", "CGV",
    "Comedy TV",
    "Drama H",
    "Dramax",
    "Sky Drama",
    "채널A",
}

# 정규화: 소문자 비교용 매핑
MAJOR_NETWORKS_LOWER = {n.lower() for n in MAJOR_NETWORKS}


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
    """TMDB search/tv로 시리즈 검색"""
    data = tmdb_get("search/tv", {
        "query": query,
        "first_air_date_year": "",
        "include_adult": "false",
    })
    if not data or not data.get("results"):
        return None
    # 한국 origin 우선
    for r in data["results"]:
        origins = r.get("origin_country", [])
        if "KR" in origins and r.get("name") == query:
            return r["id"]
    for r in data["results"]:
        origins = r.get("origin_country", [])
        if "KR" in origins:
            return r["id"]
    # 첫 번째 결과 반환
    return data["results"][0]["id"]


def get_networks(tmdb_id):
    """TV detail에서 networks 목록 추출"""
    detail = tmdb_get(f"tv/{tmdb_id}")
    if not detail:
        return []
    networks = detail.get("networks", [])
    return [n.get("name", "") for n in networks]


def is_major_network(networks):
    """주요 방송사 여부 판단"""
    for net in networks:
        if net.lower() in MAJOR_NETWORKS_LOWER:
            return True
        # 부분 매칭 (KBS2 TV → KBS)
        net_l = net.lower()
        for major in MAJOR_NETWORKS_LOWER:
            if major in net_l or net_l in major:
                return True
    return False


def main():
    dry_run = "--dry-run" in sys.argv or "--delete" not in sys.argv
    if dry_run:
        print("=== DRY RUN 모드 (실제 삭제 없음, --delete로 실행) ===\n")
    else:
        print("=== DELETE 모드 (실제 DB 삭제) ===\n")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # 1) TV 시리즈 목록 조회 (series_nm 기준)
    cur.execute("""
        SELECT DISTINCT series_nm, ct_cl, provider,
               COUNT(*) as ep_count
        FROM public.vod
        WHERE rag_source = 'TMDB_NEW_2025'
          AND ct_cl IN ('TV드라마', 'TV 연예/오락', 'TV애니메이션')
          AND series_nm IS NOT NULL
        GROUP BY series_nm, ct_cl, provider
        ORDER BY ct_cl, series_nm
    """)
    series_list = cur.fetchall()
    print(f"총 {len(series_list)}개 시리즈 조회됨\n")

    # 2) 이미 provider가 있는 시리즈 → 바로 분류
    major_series = []
    minor_series = []
    unknown_series = []

    already_classified = 0
    for series_nm, ct_cl, provider, ep_count in series_list:
        if provider:
            already_classified += 1
            # 이미 provider 있으면 주요 방송사 여부 확인
            if is_major_network([provider]):
                major_series.append((series_nm, ct_cl, provider, ep_count))
            else:
                minor_series.append((series_nm, ct_cl, provider, ep_count))
        else:
            unknown_series.append((series_nm, ct_cl, ep_count))

    print(f"이미 분류됨: {already_classified}개 (주요: {len(major_series)}, 기타: {len(minor_series)})")
    print(f"미분류 (TMDB 조회 필요): {len(unknown_series)}개\n")

    # 3) TMDB에서 networks 조회
    tmdb_results = {}  # series_nm → (networks, is_major)
    for i, (series_nm, ct_cl, ep_count) in enumerate(unknown_series):
        tmdb_id = search_tv(series_nm)
        if tmdb_id:
            networks = get_networks(tmdb_id)
            is_major = is_major_network(networks)
            tmdb_results[series_nm] = (networks, is_major, ct_cl, ep_count)
            if is_major:
                major_series.append((series_nm, ct_cl, ", ".join(networks), ep_count))
            else:
                minor_series.append((series_nm, ct_cl, ", ".join(networks) if networks else "N/A", ep_count))
        else:
            # TMDB에서 못 찾으면 → 제거 대상 (알려지지 않은 웹 콘텐츠)
            minor_series.append((series_nm, ct_cl, "NOT_FOUND", ep_count))
            tmdb_results[series_nm] = ([], False, ct_cl, ep_count)

        if (i + 1) % 20 == 0:
            print(f"  TMDB 조회 {i+1}/{len(unknown_series)}...")
        time.sleep(0.06)  # rate limit

    # 4) provider UPDATE (TMDB에서 찾은 것)
    updated = 0
    for series_nm, (networks, is_major, ct_cl, ep_count) in tmdb_results.items():
        if networks:
            provider_val = networks[0]  # 첫 번째 네트워크
            cur.execute("""
                UPDATE public.vod SET provider = %s
                WHERE series_nm = %s AND rag_source = 'TMDB_NEW_2025'
                  AND provider IS NULL
            """, (provider_val, series_nm))
            updated += cur.rowcount

    conn.commit()
    print(f"\nprovider UPDATE: {updated}건\n")

    # 5) 결과 리포트
    print("=" * 70)
    print(f"{'분류':^8} {'시리즈 수':>10} {'에피소드 수':>12}")
    print("-" * 70)

    major_eps = sum(ep for _, _, _, ep in major_series)
    minor_eps = sum(ep for _, _, _, ep in minor_series)
    print(f"{'주요방송':^8} {len(major_series):>10} {major_eps:>12}")
    print(f"{'제거대상':^8} {len(minor_series):>10} {minor_eps:>12}")
    print("=" * 70)

    # 주요 방송사 시리즈
    print(f"\n--- 주요 방송사 시리즈 ({len(major_series)}개) ---")
    for series_nm, ct_cl, provider, ep_count in sorted(major_series, key=lambda x: x[1]):
        print(f"  [{ct_cl}] {series_nm} ({provider}) - {ep_count}화")

    # 제거 대상
    print(f"\n--- 제거 대상 ({len(minor_series)}개) ---")
    for series_nm, ct_cl, provider, ep_count in sorted(minor_series, key=lambda x: x[1]):
        print(f"  [{ct_cl}] {series_nm} ({provider}) - {ep_count}화")

    # 6) 네트워크 분포
    net_dist = {}
    for series_nm, (networks, is_major, ct_cl, ep_count) in tmdb_results.items():
        key = networks[0] if networks else "N/A"
        if key not in net_dist:
            net_dist[key] = {"count": 0, "eps": 0, "major": is_major}
        net_dist[key]["count"] += 1
        net_dist[key]["eps"] += ep_count

    print(f"\n--- TMDB 네트워크 분포 ---")
    for net, info in sorted(net_dist.items(), key=lambda x: -x[1]["count"]):
        tag = "O" if info["major"] else "X"
        print(f"  [{tag}] {net:30s} : {info['count']:>4}개 시리즈, {info['eps']:>6}화")

    # 7) DELETE
    if not dry_run:
        delete_series = [s[0] for s in minor_series]
        if delete_series:
            # 안전: 먼저 삭제 건수 확인
            placeholders = ",".join(["%s"] * len(delete_series))
            cur.execute(f"""
                SELECT COUNT(*) FROM public.vod
                WHERE rag_source = 'TMDB_NEW_2025'
                  AND series_nm IN ({placeholders})
            """, delete_series)
            delete_count = cur.fetchone()[0]
            print(f"\n>>> {delete_count}건 DELETE 실행 중...")

            cur.execute(f"""
                DELETE FROM public.vod
                WHERE rag_source = 'TMDB_NEW_2025'
                  AND series_nm IN ({placeholders})
            """, delete_series)
            conn.commit()
            print(f">>> DELETE 완료: {cur.rowcount}건 삭제")
    else:
        delete_series = [s[0] for s in minor_series]
        if delete_series:
            placeholders = ",".join(["%s"] * len(delete_series))
            cur.execute(f"""
                SELECT COUNT(*) FROM public.vod
                WHERE rag_source = 'TMDB_NEW_2025'
                  AND series_nm IN ({placeholders})
            """, delete_series)
            delete_count = cur.fetchone()[0]
            print(f"\n>>> DRY RUN: {delete_count}건이 삭제될 예정 (--delete로 실행하면 삭제)")

    # 남은 VOD 통계
    cur.execute("""
        SELECT ct_cl, COUNT(*) FROM public.vod
        WHERE rag_source = 'TMDB_NEW_2025'
        GROUP BY ct_cl ORDER BY COUNT(*) DESC
    """)
    print(f"\n--- 현재 TMDB_NEW_2025 VOD 현황 ---")
    for r in cur.fetchall():
        print(f"  {r[0]:20s} : {r[1]:>6}건")

    conn.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
