"""
네이버 검색에서 TV 연예/오락 cast_guest 수집

전략 1: "회차정보" 검색 → 에피소드별 게스트 추출 (dt>출연)
전략 2: "출연진" 검색 → 시리즈 전체 출연진 → 앞 4명 cast_lead, 나머지 cast_guest

실행: python Database_Design/scripts/fill_cast_guest_from_naver.py [--dry-run] [--update]
"""

import io, sys, os, re, time, random
from urllib.request import urlopen, Request
from urllib.parse import quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://search.naver.com/",
}

CAST_LEAD_COUNT = 4  # 앞 4명은 주연(cast_lead), 나머지는 cast_guest


def _fetch_html(query):
    url = f"https://search.naver.com/search.naver?where=nexearch&ie=utf8&query={quote(query)}"
    req = Request(url)
    for k, v in HEADERS.items():
        req.add_header(k, v)
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"  [WARN] fetch fail: {query} -> {e}", file=sys.stderr)
        return None


# ─── 전략 1: 회차정보 (에피소드별 게스트) ───

def fetch_episode_info(series_nm):
    """회차정보 검색 → 에피소드별 게스트"""
    base = series_nm
    base_nocolon = re.sub(r'[:：]', ' ', base).strip()
    base_nocolon = re.sub(r'\s+', ' ', base_nocolon)

    queries = [
        f"{base} 회차정보",
        f"{base} 시즌1 회차정보",
    ]
    if base_nocolon != base:
        queries.append(f"{base_nocolon} 회차정보")

    for q in queries:
        html = _fetch_html(q)
        if html and '<dt>출연</dt>' in html:
            return parse_episode_guests(html)
        time.sleep(random.uniform(0.5, 1.0))
    return {}


def parse_episode_guests(html):
    """회차정보 HTML → {ep_num: "게스트1, 게스트2"}"""
    pattern = (
        r'<span class="num_txt">(\d+)</span>회'
        r'.*?'
        r'<span class="date_info">([\d.]+)'
        r'.*?'
        r'<dt>출연</dt>\s*<dd>(.*?)</dd>'
    )
    matches = re.findall(pattern, html, re.DOTALL)
    episodes = {}
    for ep_str, _, dd_html in matches:
        ep_num = int(ep_str)
        names = [n.strip() for n in re.findall(r'>([^<]+)</a>', dd_html) if n.strip()]
        if names:
            episodes[ep_num] = ", ".join(names)
    return episodes


# ─── 전략 2: 출연진 (시리즈 전체) ───

def fetch_cast_list(series_nm):
    """출연진 검색 → 전체 출연진 리스트"""
    base = series_nm
    base_nocolon = re.sub(r'[:：]', ' ', base).strip()
    base_nocolon = re.sub(r'\s+', ' ', base_nocolon)

    queries = [
        f"{base} 출연진",
        f"{base} 시즌1 출연진",
    ]
    if base_nocolon != base:
        queries.append(f"{base_nocolon} 출연진")

    for q in queries:
        html = _fetch_html(q)
        if html:
            names = parse_cast_names(html)
            if names:
                return names
        time.sleep(random.uniform(0.5, 1.0))
    return []


def parse_cast_names(html):
    """출연진 HTML → 이름 리스트 (순서 유지)

    _kgs_broadcast 섹션 내 <strong class="name ..."><a>이름</a></strong> 패턴
    """
    cast_section = re.search(r'_kgs_broadcast.*', html, re.DOTALL)
    if not cast_section:
        return []
    section = cast_section.group(0)[:30000]
    names = re.findall(
        r'<strong class="name[^"]*"[^>]*>.*?<a[^>]*>([^<]+)</a>',
        section, re.DOTALL
    )
    # 중복 제거 (순서 유지)
    seen = set()
    unique = []
    for n in names:
        n = n.strip()
        if n and n not in seen:
            seen.add(n)
            unique.append(n)
    return unique


def split_cast(names):
    """앞 4명 = cast_lead, 나머지 = cast_guest"""
    lead = names[:CAST_LEAD_COUNT]
    guest = names[CAST_LEAD_COUNT:]
    return ", ".join(lead), ", ".join(guest)


# ─── Main ───

def main():
    do_update = "--update" in sys.argv
    if not do_update:
        print("=== DRY RUN 모드 (--update로 실행) ===\n")
    else:
        print("=== UPDATE 모드 ===\n")

    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    # TV 연예/오락 시리즈 목록
    cur.execute("""
        SELECT DISTINCT series_nm, COUNT(*) as ep_count
        FROM public.vod
        WHERE rag_source = 'TMDB_NEW_2025'
          AND ct_cl = 'TV 연예/오락'
          AND series_nm IS NOT NULL
        GROUP BY series_nm
        ORDER BY series_nm
    """)
    series_list = cur.fetchall()
    print(f"총 {len(series_list)}개 시리즈\n")

    stats = {"ep_guest": 0, "cast_split": 0, "fail": 0}
    ep_updated = 0
    cast_updated = 0
    results = []

    for idx, (series_nm, ep_count) in enumerate(series_list):
        # 전략 1: 회차정보 (에피소드별 게스트)
        ep_guests = fetch_episode_info(series_nm)

        if ep_guests:
            matched = 0
            for ep_num, guest_str in ep_guests.items():
                ep_patterns = [
                    f"{series_nm} {str(ep_num).zfill(2)}회",
                    f"{series_nm} {str(ep_num).zfill(3)}회",
                    f"{series_nm} {ep_num}회",
                ]
                for pat in ep_patterns:
                    if do_update:
                        cur.execute("""
                            UPDATE public.vod SET cast_guest = %s
                            WHERE asset_nm = %s AND rag_source = 'TMDB_NEW_2025'
                              AND (cast_guest IS NULL OR cast_guest = '')
                        """, (guest_str, pat))
                        if cur.rowcount > 0:
                            matched += cur.rowcount
                            break
                    else:
                        cur.execute("""
                            SELECT 1 FROM public.vod
                            WHERE asset_nm = %s AND rag_source = 'TMDB_NEW_2025'
                              AND (cast_guest IS NULL OR cast_guest = '')
                            LIMIT 1
                        """, (pat,))
                        if cur.fetchone():
                            matched += 1
                            break

            if matched > 0:
                stats["ep_guest"] += 1
                ep_updated += matched
                results.append((series_nm, ep_count, f"회차별 {matched}화", "EP_GUEST"))
                if do_update:
                    conn.commit()
                if (idx + 1) % 10 == 0:
                    print(f"  진행: {idx+1}/{len(series_list)} (회차:{ep_updated}, 출연진:{cast_updated})")
                time.sleep(random.uniform(0.5, 1.0))
                continue

        # 전략 2: 출연진 목록 → cast_lead / cast_guest 분리
        cast_names = fetch_cast_list(series_nm)

        if cast_names and len(cast_names) > CAST_LEAD_COUNT:
            lead_str, guest_str = split_cast(cast_names)
            if do_update:
                cur.execute("""
                    UPDATE public.vod
                    SET cast_lead = %s, cast_guest = %s
                    WHERE series_nm = %s AND rag_source = 'TMDB_NEW_2025'
                """, (lead_str, guest_str, series_nm))
                matched = cur.rowcount
                conn.commit()
            else:
                cur.execute("""
                    SELECT COUNT(*) FROM public.vod
                    WHERE series_nm = %s AND rag_source = 'TMDB_NEW_2025'
                """, (series_nm,))
                matched = cur.fetchone()[0]

            if matched > 0:
                stats["cast_split"] += 1
                cast_updated += matched
                results.append((series_nm, ep_count,
                    f"출연진 {len(cast_names)}명 (lead:{lead_str[:30]}.. guest:{guest_str[:30]}..)",
                    "CAST_SPLIT"))
            else:
                stats["fail"] += 1
                results.append((series_nm, ep_count, "매칭실패", "FAIL"))
        elif cast_names and len(cast_names) <= CAST_LEAD_COUNT:
            # 출연진이 4명 이하면 전부 cast_lead, cast_guest 없음
            lead_str = ", ".join(cast_names)
            if do_update:
                cur.execute("""
                    UPDATE public.vod SET cast_lead = %s
                    WHERE series_nm = %s AND rag_source = 'TMDB_NEW_2025'
                      AND (cast_lead IS NULL OR cast_lead = '')
                """, (lead_str, series_nm))
                conn.commit()
            stats["fail"] += 1
            results.append((series_nm, ep_count, f"출연진 {len(cast_names)}명 (guest 없음)", "LEAD_ONLY"))
        else:
            stats["fail"] += 1
            results.append((series_nm, ep_count, "미발견", "NOT_FOUND"))

        if (idx + 1) % 10 == 0:
            print(f"  진행: {idx+1}/{len(series_list)} (회차:{ep_updated}, 출연진:{cast_updated})")

        time.sleep(random.uniform(0.5, 1.0))

    # 리포트
    print(f"\n{'=' * 70}")
    print(f"  총 시리즈: {len(series_list)}")
    print(f"  전략1 성공 (회차별 게스트): {stats['ep_guest']}개")
    print(f"  전략2 성공 (출연진 분리):   {stats['cast_split']}개")
    print(f"  실패:                      {stats['fail']}개")
    print(f"  UPDATE: 회차별 {ep_updated}건, 출연진 {cast_updated}건")
    print(f"{'=' * 70}\n")

    # 성공 목록
    print("--- 성공 시리즈 ---")
    for nm, ep_cnt, detail, tag in results:
        if tag in ("EP_GUEST", "CAST_SPLIT"):
            print(f"  [{tag}] {nm} ({ep_cnt}화) → {detail}")

    # 실패 목록
    fail_list = [(nm, ep_cnt, detail, tag) for nm, ep_cnt, detail, tag in results if tag in ("FAIL", "NOT_FOUND", "LEAD_ONLY")]
    print(f"\n--- 미매칭/실패 ({len(fail_list)}개) ---")
    for nm, ep_cnt, detail, tag in fail_list[:30]:
        print(f"  [{tag}] {nm} ({ep_cnt}화) → {detail}")
    if len(fail_list) > 30:
        print(f"  ... 외 {len(fail_list) - 30}개")

    # 커버리지
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(cast_guest) FILTER (WHERE cast_guest IS NOT NULL AND cast_guest != '') as has_guest,
            COUNT(cast_lead) FILTER (WHERE cast_lead IS NOT NULL AND cast_lead != '') as has_lead
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
