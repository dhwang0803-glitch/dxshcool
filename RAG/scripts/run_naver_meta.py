"""
네이버 검색 기반 메타데이터 통합 파이프라인
=======================================================
소스: m.search.naver.com

■ TV드라마 / TV 연예/오락  (query: {series_nm}, where=nexearch)
  JSON castList  → cast_lead (주연/진행), cast_guest (조연)
  JSON openDate  → release_date
  JSON subTitle  → rating

■ 영화  (query: {series_nm} 출연진, where=nexearch)
  HTML div.cast_box → director (감독), cast_lead (주연), cast_guest (조연)

실행:
  python run_naver_meta.py                 # dry-run (TV 100 + 영화 100)
  python run_naver_meta.py --update        # 실제 DB UPDATE
  python run_naver_meta.py --full          # 전체 시리즈
  python run_naver_meta.py --tv-only       # TV만
  python run_naver_meta.py --movie-only    # 영화만
"""
from __future__ import annotations
import asyncio, argparse, os, re, sys, time, json
sys.stdout.reconfigure(encoding='utf-8')
from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser
from dotenv import load_dotenv
load_dotenv()

SEARCH_URL_M  = 'https://m.search.naver.com/search.naver'   # TV (JSON)
SEARCH_URL_PC = 'https://search.naver.com/search.naver'      # 영화 (HTML cast_box)
MOBILE_UA     = ('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
                 'AppleWebKit/605.1.15 (KHTML, like Gecko) '
                 'Version/17.0 Mobile/15E148 Safari/604.1')
DESKTOP_UA    = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                 'AppleWebKit/537.36 (KHTML, like Gecko) '
                 'Chrome/120.0.0.0 Safari/537.36')
HEADERS_M     = {'Accept-Language': 'ko-KR,ko;q=0.9', 'User-Agent': MOBILE_UA,
                 'Referer': 'https://m.search.naver.com/'}
HEADERS_PC    = {'Accept-Language': 'ko-KR,ko;q=0.9', 'User-Agent': DESKTOP_UA,
                 'Referer': 'https://search.naver.com/'}
CONCURRENCY   = 5
REQUEST_DELAY = 0.4
MAX_CAST      = 8   # cast_lead / cast_guest 최대 인원

_RATING_VALID = {'전체관람가', '12세이상', '15세이상', '19세이상', '청소년관람불가'}
_TV_CT        = ('TV드라마', 'TV 연예/오락')
_LEAD_ROLES   = {'주연', '진행'}
_GUEST_ROLES  = {'조연', '패널', '게스트'}


# ── 공통 유틸 ───────────────────────────────────────────────────
def _balanced(text: str, start: int) -> str | None:
    open_c  = text[start]
    close_c = '}' if open_c == '{' else ']'
    depth, in_str, escape = 0, False, False
    for i, c in enumerate(text[start:], start):
        if escape:              escape = False;  continue
        if c == '\\' and in_str: escape = True;  continue
        if c == '"':            in_str = not in_str; continue
        if in_str:              continue
        if c == open_c:         depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# ── TV 파서 (JSON) ───────────────────────────────────────────────
def parse_tv(html: str) -> dict:
    """castList(역할별) + openDate + subTitle(rating) 추출"""
    result = {'cast_lead': None, 'cast_guest': None,
              'release_date': None, 'rating': None}

    # castList
    m = re.search(r'"castList"\s*:\s*\{', html)
    if m:
        raw = _balanced(html, m.end() - 1)
        if raw:
            try:
                d = json.loads(raw)
                leads  = [c['name'] for c in d.get('casts', [])
                          if c.get('role') in _LEAD_ROLES  and c.get('name')][:MAX_CAST]
                guests = [c['name'] for c in d.get('casts', [])
                          if c.get('role') in _GUEST_ROLES and c.get('name')][:MAX_CAST]
                if leads:  result['cast_lead']  = ', '.join(leads)
                if guests: result['cast_guest'] = ', '.join(guests)
            except Exception:
                pass

    # openDate → release_date
    m2 = re.search(r'"openDate"\s*:\s*"(\d{4}-\d{2}-\d{2})"', html)
    if m2:
        result['release_date'] = m2.group(1)

    # subTitle → rating
    for m3 in re.finditer(r'"subTitle"\s*:\s*\[', html):
        raw = _balanced(html, m3.end() - 1)
        if not raw:
            continue
        try:
            for item in json.loads(raw):
                t = item.get('text', '')
                if t in _RATING_VALID:
                    result['rating'] = t
                    break
        except Exception:
            pass
        if result['rating']:
            break

    return result


# ── 영화 파서 (HTML cast_box) ────────────────────────────────────
def parse_movie(html: str) -> dict:
    """div.cast_box 섹션 → director, cast_lead (주연), cast_guest (조연)"""
    result = {'director': None, 'cast_lead': None, 'cast_guest': None}
    tree   = HTMLParser(html)
    seen   = set()  # 중복 섹션 제거 (Naver가 동일 블록을 2회 렌더링)

    for box in tree.css('div.cast_box'):
        h3 = box.css_first('h3.title_numbering')
        if not h3:
            continue
        section = h3.text(strip=True)
        if section in seen:
            continue
        seen.add(section)

        names = [n.text(strip=True) for n in box.css('strong.name span')
                 if n.text(strip=True)]

        if section == '감독' and names and not result['director']:
            result['director'] = names[0]
        elif section == '주연' and names and not result['cast_lead']:
            result['cast_lead'] = ', '.join(names[:MAX_CAST])
        elif section == '조연' and names and not result['cast_guest']:
            result['cast_guest'] = ', '.join(names[:MAX_CAST])

    return result


# ── 네이버 검색 ─────────────────────────────────────────────────
async def search_tv(sess: AsyncSession, series_nm: str,
                    sem: asyncio.Semaphore) -> dict:
    out = {'series_nm': series_nm, 'cast_lead': None, 'cast_guest': None,
           'release_date': None, 'rating': None, 'error': None}
    async with sem:
        await asyncio.sleep(REQUEST_DELAY)
        try:
            r = await sess.get(SEARCH_URL_M,
                               params={'query': series_nm, 'where': 'nexearch'},
                               headers=HEADERS_M, timeout=12)
            out.update(parse_tv(r.text))
        except Exception as e:
            out['error'] = str(e)[:60]
    return out


async def search_movie(sess: AsyncSession, series_nm: str,
                       sem: asyncio.Semaphore) -> dict:
    out = {'series_nm': series_nm, 'director': None,
           'cast_lead': None, 'cast_guest': None, 'error': None}
    async with sem:
        await asyncio.sleep(REQUEST_DELAY)
        try:
            # PC Naver: 영화 출연진 페이지 → HTML cast_box 구조
            r = await sess.get(SEARCH_URL_PC,
                               params={'query': f'{series_nm} 출연진',
                                       'where': 'nexearch'},
                               headers=HEADERS_PC, timeout=12)
            out.update(parse_movie(r.text))
        except Exception as e:
            out['error'] = str(e)[:60]
    return out


# ── DB 헬퍼 ────────────────────────────────────────────────────
def get_conn():
    import psycopg2
    return psycopg2.connect(
        host=os.getenv('DB_HOST'), port=int(os.getenv('DB_PORT', '5432')),
        dbname=os.getenv('DB_NAME'), user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
    )


def get_tv_targets(limit: int | None = 100) -> list[dict]:
    conn = get_conn(); cur = conn.cursor()
    lim = f'LIMIT {limit}' if limit else ''
    cur.execute(f"""
        SELECT series_nm, ct_cl,
               COUNT(*) AS ep_cnt,
               SUM(CASE WHEN cast_lead    IS NULL THEN 1 ELSE 0 END) AS cl_null,
               SUM(CASE WHEN cast_guest   IS NULL THEN 1 ELSE 0 END) AS cg_null,
               SUM(CASE WHEN release_date IS NULL THEN 1 ELSE 0 END) AS rd_null,
               SUM(CASE WHEN rating       IS NULL THEN 1 ELSE 0 END) AS rt_null
        FROM vod
        WHERE ct_cl IN ('TV드라마', 'TV 연예/오락')
          AND series_nm IS NOT NULL
          AND (cast_lead IS NULL OR cast_guest IS NULL
               OR release_date IS NULL OR rating IS NULL)
        GROUP BY series_nm, ct_cl
        ORDER BY ep_cnt DESC
        {lim}
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    return [{'series_nm': r[0], 'ct_cl': r[1], 'ep_cnt': r[2],
             'cl_null': r[3], 'cg_null': r[4], 'rd_null': r[5], 'rt_null': r[6]}
            for r in rows]


_CACHE_PATH = 'RAG/data/bulk/series_cache.json'

def _load_cache_movie_names() -> set[str]:
    """series_cache에서 media_type=movie인 실제 영화 제목 반환"""
    if not os.path.exists(_CACHE_PATH):
        return set()
    with open(_CACHE_PATH, encoding='utf-8') as f:
        cache = json.load(f)
    return {nm for nm, info in cache.items() if info.get('media_type') == 'movie'}


def get_movie_targets(limit: int | None = 100) -> list[dict]:
    """TMDB 캐시에 있는 실제 영화만 타겟 (장르 라벨 제외)"""
    valid_names = _load_cache_movie_names()
    if not valid_names:
        return []

    conn = get_conn(); cur = conn.cursor()
    lim = f'LIMIT {limit}' if limit else ''
    cur.execute(f"""
        SELECT series_nm, ct_cl,
               COUNT(*) AS ep_cnt,
               SUM(CASE WHEN director   IS NULL THEN 1 ELSE 0 END) AS dir_null,
               SUM(CASE WHEN cast_lead  IS NULL THEN 1 ELSE 0 END) AS cl_null,
               SUM(CASE WHEN cast_guest IS NULL THEN 1 ELSE 0 END) AS cg_null
        FROM vod
        WHERE ct_cl = '영화'
          AND series_nm IS NOT NULL
          AND (director IS NULL OR cast_lead IS NULL OR cast_guest IS NULL)
        GROUP BY series_nm, ct_cl
        ORDER BY ep_cnt DESC
        {lim}
    """)
    rows = cur.fetchall(); cur.close(); conn.close()
    # Python 단에서 캐시 검증 필터
    return [{'series_nm': r[0], 'ct_cl': r[1], 'ep_cnt': r[2],
             'dir_null': r[3], 'cl_null': r[4], 'cg_null': r[5]}
            for r in rows if r[0] in valid_names]


# ── DB UPDATE ──────────────────────────────────────────────────
def bulk_update(tv_results: list[dict], movie_results: list[dict],
                dry_run: bool = True) -> dict:
    stats = {'tv_cl': 0, 'tv_cg': 0, 'tv_rd': 0, 'tv_rt': 0,
             'mv_dir': 0, 'mv_cl': 0, 'mv_cg': 0,
             'tv_cl_rows': 0, 'tv_cg_rows': 0, 'tv_rd_rows': 0, 'tv_rt_rows': 0,
             'mv_dir_rows': 0, 'mv_cl_rows': 0, 'mv_cg_rows': 0,
             'dry_run': dry_run}

    if dry_run:
        # 예상치만 계산
        for r in tv_results:
            if r.get('cast_lead'):    stats['tv_cl']  += 1
            if r.get('cast_guest'):   stats['tv_cg']  += 1
            if r.get('release_date'): stats['tv_rd']  += 1
            if r.get('rating'):       stats['tv_rt']  += 1
        for r in movie_results:
            if r.get('director'):   stats['mv_dir'] += 1
            if r.get('cast_lead'):  stats['mv_cl']  += 1
            if r.get('cast_guest'): stats['mv_cg']  += 1
        return stats

    conn = get_conn(); cur = conn.cursor()

    # TV UPDATE
    for r in tv_results:
        nm = r['series_nm']
        if r.get('cast_lead'):
            cur.execute("""
                UPDATE vod SET cast_lead = %s,
                    rag_processed=TRUE, rag_source='naver_meta',
                    rag_processed_at=NOW()
                WHERE series_nm=%s AND cast_lead IS NULL
            """, (r['cast_lead'], nm))
            n = cur.rowcount
            if n: stats['tv_cl'] += 1; stats['tv_cl_rows'] += n

        if r.get('cast_guest'):
            cur.execute("""
                UPDATE vod SET cast_guest = %s,
                    rag_processed=TRUE, rag_source='naver_meta',
                    rag_processed_at=NOW()
                WHERE series_nm=%s AND cast_guest IS NULL
            """, (r['cast_guest'], nm))
            n = cur.rowcount
            if n: stats['tv_cg'] += 1; stats['tv_cg_rows'] += n

        if r.get('release_date'):
            cur.execute("""
                UPDATE vod SET release_date = %s,
                    rag_processed=TRUE, rag_source='naver_meta',
                    rag_processed_at=NOW()
                WHERE series_nm=%s AND release_date IS NULL
            """, (r['release_date'], nm))
            n = cur.rowcount
            if n: stats['tv_rd'] += 1; stats['tv_rd_rows'] += n

        if r.get('rating'):
            cur.execute("""
                UPDATE vod SET rating = %s,
                    rag_processed=TRUE,
                    rag_source=COALESCE(rag_source,'naver_meta'),
                    rag_processed_at=NOW()
                WHERE series_nm=%s AND rating IS NULL
            """, (r['rating'], nm))
            n = cur.rowcount
            if n: stats['tv_rt'] += 1; stats['tv_rt_rows'] += n

    # 영화 UPDATE
    for r in movie_results:
        nm = r['series_nm']
        if r.get('director'):
            cur.execute("""
                UPDATE vod SET director = %s,
                    rag_processed=TRUE, rag_source='naver_meta',
                    rag_processed_at=NOW()
                WHERE series_nm=%s AND director IS NULL
            """, (r['director'], nm))
            n = cur.rowcount
            if n: stats['mv_dir'] += 1; stats['mv_dir_rows'] += n

        if r.get('cast_lead'):
            cur.execute("""
                UPDATE vod SET cast_lead = %s,
                    rag_processed=TRUE, rag_source='naver_meta',
                    rag_processed_at=NOW()
                WHERE series_nm=%s AND cast_lead IS NULL
            """, (r['cast_lead'], nm))
            n = cur.rowcount
            if n: stats['mv_cl'] += 1; stats['mv_cl_rows'] += n

        if r.get('cast_guest'):
            cur.execute("""
                UPDATE vod SET cast_guest = %s,
                    rag_processed=TRUE, rag_source='naver_meta',
                    rag_processed_at=NOW()
                WHERE series_nm=%s AND cast_guest IS NULL
            """, (r['cast_guest'], nm))
            n = cur.rowcount
            if n: stats['mv_cg'] += 1; stats['mv_cg_rows'] += n

    conn.commit(); cur.close(); conn.close()
    return stats


# ── 출력 헬퍼 ──────────────────────────────────────────────────
def _pct(a, b): return f'{a/b*100:.0f}%' if b else '-'


# ── 메인 ──────────────────────────────────────────────────────
async def main(args):
    print('=' * 64)
    print('네이버 메타데이터 통합 파이프라인')
    print(f'모드: {"실제 UPDATE" if args.update else "DRY-RUN"}')
    print('=' * 64)

    limit = None if args.full else 100
    tv_targets    = [] if args.movie_only else get_tv_targets(limit)
    movie_targets = [] if args.tv_only    else get_movie_targets(limit)

    print(f'\nTV 타겟:  {len(tv_targets):,}개 시리즈')
    print(f'영화 타겟: {len(movie_targets):,}개 시리즈')

    sem = asyncio.Semaphore(CONCURRENCY)
    t0  = time.perf_counter()

    async with AsyncSession(impersonate='chrome120') as sess:
        # TV 검색
        tv_results = []
        if tv_targets:
            print(f'\n[TV 검색 시작] {len(tv_targets)}개...')
            tasks = [search_tv(sess, t['series_nm'], sem) for t in tv_targets]
            tv_results = await asyncio.gather(*tasks)

        # 영화 검색
        movie_results = []
        if movie_targets:
            print(f'\n[영화 검색 시작] {len(movie_targets)}개...')
            tasks = [search_movie(sess, t['series_nm'], sem) for t in movie_targets]
            movie_results = await asyncio.gather(*tasks)

    elapsed = time.perf_counter() - t0
    total   = len(tv_results) + len(movie_results)

    # ── 집계 ──────────────────────────────────────────────────
    tv_cl  = sum(1 for r in tv_results if r.get('cast_lead'))
    tv_cg  = sum(1 for r in tv_results if r.get('cast_guest'))
    tv_rd  = sum(1 for r in tv_results if r.get('release_date'))
    tv_rt  = sum(1 for r in tv_results if r.get('rating'))
    mv_dir = sum(1 for r in movie_results if r.get('director'))
    mv_cl  = sum(1 for r in movie_results if r.get('cast_lead'))
    mv_cg  = sum(1 for r in movie_results if r.get('cast_guest'))
    tv_err = sum(1 for r in tv_results    if r.get('error'))
    mv_err = sum(1 for r in movie_results if r.get('error'))

    n_tv = len(tv_results); n_mv = len(movie_results)

    print(f'\n{"="*64}')
    print(f'결과 ({total}건, {elapsed:.1f}초, {elapsed/max(total,1):.2f}초/건)')
    print(f'{"="*64}')
    if n_tv:
        print(f'\n[TV드라마/연예] {n_tv}개 시리즈')
        print(f'  cast_lead   : {tv_cl:4d}/{n_tv} ({_pct(tv_cl,n_tv)})')
        print(f'  cast_guest  : {tv_cg:4d}/{n_tv} ({_pct(tv_cg,n_tv)})')
        print(f'  release_date: {tv_rd:4d}/{n_tv} ({_pct(tv_rd,n_tv)})')
        print(f'  rating      : {tv_rt:4d}/{n_tv} ({_pct(tv_rt,n_tv)})')
        print(f'  에러         : {tv_err}건')
    if n_mv:
        print(f'\n[영화] {n_mv}개 시리즈')
        print(f'  director    : {mv_dir:4d}/{n_mv} ({_pct(mv_dir,n_mv)})')
        print(f'  cast_lead   : {mv_cl:4d}/{n_mv} ({_pct(mv_cl,n_mv)})')
        print(f'  cast_guest  : {mv_cg:4d}/{n_mv} ({_pct(mv_cg,n_mv)})')
        print(f'  에러         : {mv_err}건')

    # 샘플
    print(f'\n{"─"*64}')
    print('TV 성공 샘플:')
    shown = 0
    for r in tv_results:
        if (r.get('cast_lead') or r.get('release_date')) and shown < 4:
            print(f"  [{r['series_nm']}]")
            if r.get('cast_lead'):    print(f"    cast_lead:    {r['cast_lead']}")
            if r.get('cast_guest'):   print(f"    cast_guest:   {r['cast_guest']}")
            if r.get('release_date'): print(f"    release_date: {r['release_date']}")
            if r.get('rating'):       print(f"    rating:       {r['rating']}")
            shown += 1

    print('\n영화 성공 샘플:')
    shown = 0
    for r in movie_results:
        if r.get('director') and shown < 4:
            print(f"  [{r['series_nm']}] 감독={r['director']} "
                  f"| 주연={r.get('cast_lead','?')[:40] if r.get('cast_lead') else '없음'} "
                  f"| 조연={r.get('cast_guest','?')[:30] if r.get('cast_guest') else '없음'}")
            shown += 1

    # ── DB UPDATE ────────────────────────────────────────────
    print(f'\n{"="*64}')
    if not args.update:
        print('DRY-RUN: DB UPDATE 생략 (--update 플래그로 실행)')
        stats = bulk_update(list(tv_results), list(movie_results), dry_run=True)
        print(f'  예상 TV:   cast_lead {stats["tv_cl"]}시리즈, cast_guest {stats["tv_cg"]}시리즈, '
              f'release_date {stats["tv_rd"]}시리즈, rating {stats["tv_rt"]}시리즈')
        print(f'  예상 영화: director {stats["mv_dir"]}시리즈, '
              f'cast_lead {stats["mv_cl"]}시리즈, cast_guest {stats["mv_cg"]}시리즈')
    else:
        print('DB UPDATE 실행 중...')
        stats = bulk_update(list(tv_results), list(movie_results), dry_run=False)
        print(f'\n  TV드라마/연예:')
        print(f'    cast_lead   : {stats["tv_cl"]}시리즈, {stats["tv_cl_rows"]:,}건')
        print(f'    cast_guest  : {stats["tv_cg"]}시리즈, {stats["tv_cg_rows"]:,}건')
        print(f'    release_date: {stats["tv_rd"]}시리즈, {stats["tv_rd_rows"]:,}건')
        print(f'    rating      : {stats["tv_rt"]}시리즈, {stats["tv_rt_rows"]:,}건')
        print(f'  영화:')
        print(f'    director    : {stats["mv_dir"]}시리즈, {stats["mv_dir_rows"]:,}건')
        print(f'    cast_lead   : {stats["mv_cl"]}시리즈, {stats["mv_cl_rows"]:,}건')
        print(f'    cast_guest  : {stats["mv_cg"]}시리즈, {stats["mv_cg_rows"]:,}건')

    # JSON 저장
    out = 'RAG/data/naver_meta_results.json'
    os.makedirs('RAG/data', exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'tv': list(tv_results), 'movie': list(movie_results)},
                  f, ensure_ascii=False, indent=2)
    print(f'\n결과 저장: {out}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--update',      action='store_true', help='실제 DB UPDATE')
    parser.add_argument('--full',        action='store_true', help='전체 시리즈 실행')
    parser.add_argument('--tv-only',     action='store_true', help='TV만 실행')
    parser.add_argument('--movie-only',  action='store_true', help='영화만 실행')
    args = parser.parse_args()
    asyncio.run(main(args))
