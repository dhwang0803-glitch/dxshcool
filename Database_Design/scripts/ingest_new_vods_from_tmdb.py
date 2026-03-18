"""
TMDB → vod 테이블 신규 VOD 수집 스크립트

대상: 2025-01-01 ~ 2026-03-18 한국 개봉/방영 콘텐츠
  - 영화: 한국 극장 개봉 전체 (해외 포함), 다큐/단편 제외, VC>=5, runtime>=60
  - TV 드라마: origin_country=KR, genre=18
  - TV 예능: origin_country=KR, genre=10764|10767
  - 애니메이션: origin_country=KR, genre=16 (영화+TV)

실행: python Database_Design/scripts/ingest_new_vods_from_tmdb.py
"""

import io, sys, os, json, time, random, string, re
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from datetime import datetime

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

# ─── Config ───
DATE_FROM = "2025-01-01"
DATE_TO = "2026-03-18"
BASE = "https://api.themoviedb.org/3"
API_KEY = os.getenv("TMDB_API_KEY")
M_NUMBER_START = 5200000  # 기존 max=5150922, 충분한 갭

# ─── TMDB helpers ───

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
                print(f"  [WARN] API fail: {endpoint} → {e}", file=sys.stderr)
                return None


def discover_all_pages(endpoint, params):
    """Discover API 전체 페이지 순회"""
    results = []
    page = 1
    while True:
        p = dict(params)
        p["page"] = page
        data = tmdb_get(endpoint, p)
        if not data or not data.get("results"):
            break
        results.extend(data["results"])
        if page >= data.get("total_pages", 1):
            break
        page += 1
        time.sleep(0.05)
    return results


def get_detail(media_type, tmdb_id):
    """영화/TV detail + credits + videos + ratings"""
    append = "credits,videos"
    if media_type == "movie":
        append += ",release_dates"
    else:
        append += ",content_ratings"
    return tmdb_get(f"{media_type}/{tmdb_id}", {"append_to_response": append})


def extract_kr_rating(detail, media_type):
    if media_type == "movie":
        for r in detail.get("release_dates", {}).get("results", []):
            if r.get("iso_3166_1") == "KR":
                dates = r.get("release_dates", [])
                if dates:
                    cert = dates[0].get("certification", "")
                    if cert:
                        return cert
    else:
        for r in detail.get("content_ratings", {}).get("results", []):
            if r.get("iso_3166_1") == "KR":
                return r.get("rating", "")
    return None


def extract_youtube_trailer(detail):
    videos = detail.get("videos", {}).get("results", [])
    # 한국어 트레일러 우선
    for v in videos:
        if v.get("type") == "Trailer" and v.get("site") == "YouTube" and v.get("iso_639_1") == "ko":
            return v["key"]
    for v in videos:
        if v.get("type") == "Trailer" and v.get("site") == "YouTube":
            return v["key"]
    for v in videos:
        if v.get("site") == "YouTube":
            return v["key"]
    return None


def media_type_to_ct_cl(media_type, genres, is_animation=False):
    """TMDB 정보 → ct_cl 매핑"""
    genre_names = [g["name"] if isinstance(g, dict) else g for g in genres]
    if is_animation:
        if media_type == "movie":
            return "TV애니메이션"  # IPTV에서는 애니 영화도 TV애니메이션으로 분류
        return "TV애니메이션"
    if media_type == "movie":
        return "영화"
    # TV
    if any(g in genre_names for g in ["드라마", "Drama"]):
        return "TV드라마"
    if any(g in genre_names for g in ["Reality", "Talk"]):
        return "TV 연예/오락"
    if any(g in genre_names for g in ["Comedy", "코미디"]):
        return "TV 연예/오락"
    return "TV드라마"


# ─── ID generator ───

_m_counter = M_NUMBER_START

def generate_full_asset_id():
    """cjc|M{7}L{S/F}{OI}{8} 형식 생성"""
    global _m_counter
    _m_counter += 1
    m_num = str(_m_counter).zfill(7)
    mid = "LSGT"  # T = TMDB sourced (기존에 없는 코드로 출처 구분)
    suffix = str(random.randint(10000000, 99999999))
    return f"cjc|M{m_num}{mid}{suffix}"


# ─── Discover ───

def discover_movies():
    """한국 극장 개봉 영화 (해외 포함), 다큐/단편 제외"""
    print("[1/4] 영화 discover...")
    return discover_all_pages("discover/movie", {
        "region": "KR",
        "with_release_type": "3",
        "release_date.gte": DATE_FROM,
        "release_date.lte": DATE_TO,
        "without_genres": "99",
        "vote_count.gte": "5",
        "with_runtime.gte": "60",
        "sort_by": "release_date.desc",
    })


def discover_tv(genre_id, label):
    print(f"[discover] TV {label} (genre={genre_id})...")
    return discover_all_pages("discover/tv", {
        "with_origin_country": "KR",
        "first_air_date.gte": DATE_FROM,
        "first_air_date.lte": DATE_TO,
        "with_genres": str(genre_id),
        "sort_by": "first_air_date.desc",
    })


def discover_animation():
    print("[discover] 애니메이션...")
    movies = discover_all_pages("discover/movie", {
        "with_origin_country": "KR",
        "primary_release_date.gte": DATE_FROM,
        "primary_release_date.lte": DATE_TO,
        "with_genres": "16",
        "sort_by": "primary_release_date.desc",
    })
    tvs = discover_all_pages("discover/tv", {
        "with_origin_country": "KR",
        "first_air_date.gte": DATE_FROM,
        "first_air_date.lte": DATE_TO,
        "with_genres": "16",
        "sort_by": "first_air_date.desc",
    })
    for m in movies:
        m["_media_type"] = "movie"
    for t in tvs:
        t["_media_type"] = "tv"
    return movies + tvs


# ─── TV 에피소드 확장 ───

def expand_tv_episodes(tv_item, detail):
    """TV 시리즈 → 에피소드별 VOD 행 생성"""
    episodes = []
    n_seasons = detail.get("number_of_seasons", 1) or 1
    n_episodes = detail.get("number_of_episodes", 1) or 1
    series_name = detail.get("name", tv_item.get("name", ""))

    if n_seasons <= 1 and n_episodes <= 200:
        # 단일 시즌: "{시리즈명} 01회" ~ "{시리즈명} {n}회"
        for ep in range(1, n_episodes + 1):
            ep_str = str(ep).zfill(2) if n_episodes < 100 else str(ep).zfill(3)
            episodes.append({
                "asset_nm": f"{series_name} {ep_str}회",
                "series_nm": series_name,
                "episode": ep,
                "season": 1,
            })
    elif n_seasons > 1:
        # 다중 시즌: 시즌별 에피소드 조회
        for s in range(1, min(n_seasons + 1, 20)):  # 최대 20시즌
            season_data = tmdb_get(f"tv/{detail['id']}/season/{s}")
            if not season_data:
                continue
            eps = season_data.get("episodes", [])
            for ep_info in eps:
                ep_num = ep_info.get("episode_number", 1)
                ep_str = str(ep_num).zfill(2)
                if n_seasons > 1:
                    asset_nm = f"{series_name} {s}기 {ep_str}회"
                else:
                    asset_nm = f"{series_name} {ep_str}회"
                episodes.append({
                    "asset_nm": asset_nm,
                    "series_nm": series_name,
                    "episode": ep_num,
                    "season": s,
                })
            time.sleep(0.05)
    else:
        # 에피소드 200+는 시리즈 단위로만
        episodes.append({
            "asset_nm": series_name,
            "series_nm": series_name,
            "episode": None,
            "season": None,
        })

    return episodes


# ─── Build VOD row ───

def build_vod_row(item, media_type, detail, is_animation=False, ep_override=None):
    """TMDB detail → vod 테이블 행"""
    if not detail:
        return None

    credits = detail.get("credits", {})
    cast = credits.get("cast", [])
    crew = credits.get("crew", [])

    directors = [c["name"] for c in crew if c.get("job") in ("Director", "Series Director")]
    lead_cast = [c["name"] for c in cast[:5]]

    genres = detail.get("genres", [])
    genre_names = [g["name"] for g in genres]

    runtime = detail.get("runtime") or (detail.get("episode_run_time", [None]) or [None])[0]

    ct_cl = media_type_to_ct_cl(media_type, genres, is_animation)

    if media_type == "movie":
        release_date = detail.get("release_date")
        asset_nm = detail.get("title", "")
        series_nm = None
    else:
        release_date = detail.get("first_air_date")
        asset_nm = detail.get("name", "")
        series_nm = asset_nm

    # episode override
    if ep_override:
        asset_nm = ep_override.get("asset_nm", asset_nm)
        series_nm = ep_override.get("series_nm", series_nm)

    row = {
        "full_asset_id": generate_full_asset_id(),
        "asset_nm": asset_nm,
        "ct_cl": ct_cl,
        "disp_rtm": f"{runtime // 60:02d}:{runtime % 60:02d}" if runtime else None,
        "disp_rtm_sec": runtime * 60 if runtime else None,
        "genre": genre_names[0] if genre_names else None,
        "director": ", ".join(directors) if directors else None,
        "asset_prod": detail.get("production_companies", [{}])[0].get("name") if detail.get("production_companies") else None,
        "smry": detail.get("overview") or None,
        "genre_detail": ", ".join(genre_names) if genre_names else None,
        "series_nm": series_nm,
        "release_date": release_date if release_date else None,
        "rating": extract_kr_rating(detail, media_type),
        "cast_lead": ", ".join(lead_cast) if lead_cast else None,
        "poster_url": f"https://image.tmdb.org/t/p/w500{detail['poster_path']}" if detail.get("poster_path") else None,
        # youtube_video_id, duration_sec → 마이그레이션 미적용 상태이므로 _meta에만 보관
        "_youtube_video_id": extract_youtube_trailer(detail),
        "_duration_sec": runtime * 60 if runtime else None,
        "rag_processed": True,
        "rag_source": "TMDB_NEW_2025",
        "rag_processed_at": datetime.now(tz=None).isoformat(),
        "rag_confidence": 0.95,
    }
    return row


# ─── DB insert ───

INSERT_SQL = """
INSERT INTO vod (
    full_asset_id, asset_nm, ct_cl, disp_rtm, disp_rtm_sec,
    genre, director, asset_prod, smry, genre_detail,
    series_nm, release_date, rating, cast_lead,
    poster_url,
    rag_processed, rag_source, rag_processed_at, rag_confidence
) VALUES (
    %(full_asset_id)s, %(asset_nm)s, %(ct_cl)s, %(disp_rtm)s, %(disp_rtm_sec)s,
    %(genre)s, %(director)s, %(asset_prod)s, %(smry)s, %(genre_detail)s,
    %(series_nm)s, %(release_date)s, %(rating)s, %(cast_lead)s,
    %(poster_url)s,
    %(rag_processed)s, %(rag_source)s, %(rag_processed_at)s, %(rag_confidence)s
)
"""


def main():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    conn.autocommit = False
    cur = conn.cursor()

    all_rows = []
    stats = {"movie": 0, "drama": 0, "variety": 0, "animation": 0}
    detail_cache = {}  # tmdb_id → detail (중복 방지)

    # ─── 1. 영화 ───
    movies = discover_movies()
    print(f"  영화 discover: {len(movies)}건")
    for i, m in enumerate(movies):
        tid = m["id"]
        if tid in detail_cache:
            continue
        detail = get_detail("movie", tid)
        detail_cache[tid] = detail
        if not detail:
            continue
        row = build_vod_row(m, "movie", detail)
        if row:
            all_rows.append(row)
            stats["movie"] += 1
        if (i + 1) % 50 == 0:
            print(f"  영화 {i+1}/{len(movies)}...")
        time.sleep(0.03)

    # ─── 2. TV 드라마 ───
    print("[2/4] TV 드라마 discover...")
    dramas = discover_tv(18, "드라마")
    print(f"  드라마 discover: {len(dramas)}건 (시리즈)")
    for i, d in enumerate(dramas):
        tid = d["id"]
        if tid in detail_cache:
            continue
        detail = get_detail("tv", tid)
        detail_cache[tid] = detail
        if not detail:
            continue
        episodes = expand_tv_episodes(d, detail)
        for ep in episodes:
            row = build_vod_row(d, "tv", detail, ep_override=ep)
            if row:
                all_rows.append(row)
                stats["drama"] += 1
        if (i + 1) % 30 == 0:
            print(f"  드라마 {i+1}/{len(dramas)}... (rows so far: {len(all_rows)})")
        time.sleep(0.03)

    # ─── 3. TV 예능 ───
    print("[3/4] TV 예능 discover...")
    variety_reality = discover_tv(10764, "리얼리티")
    variety_talk = discover_tv(10767, "토크쇼")
    # 중복 제거
    seen_tv = set()
    variety = []
    for v in variety_reality + variety_talk:
        if v["id"] not in seen_tv:
            seen_tv.add(v["id"])
            variety.append(v)
    print(f"  예능 discover: {len(variety)}건 (시리즈, 중복제거)")
    for i, v in enumerate(variety):
        tid = v["id"]
        if tid in detail_cache:
            continue
        detail = get_detail("tv", tid)
        detail_cache[tid] = detail
        if not detail:
            continue
        episodes = expand_tv_episodes(v, detail)
        for ep in episodes:
            row = build_vod_row(v, "tv", detail, ep_override=ep)
            if row and row["ct_cl"] != "TV드라마":
                pass  # keep as-is
            if row:
                row["ct_cl"] = "TV 연예/오락"
                all_rows.append(row)
                stats["variety"] += 1
        if (i + 1) % 30 == 0:
            print(f"  예능 {i+1}/{len(variety)}... (rows so far: {len(all_rows)})")
        time.sleep(0.03)

    # ─── 4. 애니메이션 ───
    print("[4/4] 애니메이션 discover...")
    anims = discover_animation()
    print(f"  애니 discover: {len(anims)}건")
    for i, a in enumerate(anims):
        tid = a["id"]
        mt = a.get("_media_type", "movie")
        if tid in detail_cache:
            continue
        detail = get_detail(mt, tid)
        detail_cache[tid] = detail
        if not detail:
            continue
        if mt == "tv":
            episodes = expand_tv_episodes(a, detail)
            for ep in episodes:
                row = build_vod_row(a, mt, detail, is_animation=True, ep_override=ep)
                if row:
                    all_rows.append(row)
                    stats["animation"] += 1
        else:
            row = build_vod_row(a, mt, detail, is_animation=True)
            if row:
                all_rows.append(row)
                stats["animation"] += 1
        if (i + 1) % 30 == 0:
            print(f"  애니 {i+1}/{len(anims)}... (rows so far: {len(all_rows)})")
        time.sleep(0.03)

    # ─── Insert (배치) ───
    print(f"\n=== 총 {len(all_rows)}건 INSERT 시작 ===")
    print(f"  영화: {stats['movie']}, 드라마: {stats['drama']}, 예능: {stats['variety']}, 애니: {stats['animation']}")

    success = 0
    fail = 0
    batch_size = 100
    for batch_start in range(0, len(all_rows), batch_size):
        batch = all_rows[batch_start:batch_start + batch_size]
        for row in batch:
            try:
                cur.execute(INSERT_SQL, row)
                success += 1
            except Exception as e:
                conn.rollback()
                fail += 1
                if fail <= 5:
                    print(f"  [ERR] {row['asset_nm'][:30]}: {str(e)[:80]}", file=sys.stderr)
        conn.commit()
        if (batch_start + batch_size) % 1000 == 0:
            print(f"  inserted {batch_start + len(batch)}/{len(all_rows)}...")

    print(f"\n=== INSERT 완료: 성공 {success}, 실패 {fail} ===")

    # ─── 컬럼별 NULL 비율 ───
    columns = [
        "asset_nm", "ct_cl", "disp_rtm", "disp_rtm_sec", "genre",
        "director", "asset_prod", "smry", "genre_detail", "series_nm",
        "release_date", "rating", "cast_lead", "poster_url",
    ]
    print("\n=== 신규 VOD 컬럼별 NULL 비율 ===")
    cur.execute(f"""
        SELECT COUNT(*) FROM vod WHERE rag_source = 'TMDB_NEW_2025'
    """)
    total = cur.fetchone()[0]
    print(f"총 신규 VOD: {total}건")
    for col in columns:
        cur.execute(f"""
            SELECT COUNT(*) FROM vod
            WHERE rag_source = 'TMDB_NEW_2025' AND {col} IS NULL
        """)
        null_cnt = cur.fetchone()[0]
        pct = null_cnt / total * 100 if total > 0 else 0
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        print(f"  {col:20s} : {null_cnt:>5}/{total} ({pct:5.1f}%) {bar}")

    # ─── ct_cl 분포 ───
    print("\n=== 신규 VOD ct_cl 분포 ===")
    cur.execute("""
        SELECT ct_cl, COUNT(*) FROM vod
        WHERE rag_source = 'TMDB_NEW_2025'
        GROUP BY ct_cl ORDER BY COUNT(*) DESC
    """)
    for r in cur.fetchall():
        print(f"  {r[0]:20s} : {r[1]:>6,}건")

    conn.close()
    print("\n완료!")


if __name__ == "__main__":
    main()
