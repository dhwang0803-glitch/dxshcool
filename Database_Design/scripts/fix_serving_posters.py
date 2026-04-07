"""
서빙 테이블 노출 VOD 포스터 일괄 교체 스크립트

서빙 테이블(tag_recommendation, hybrid_recommendation, popular_recommendation)에
노출되는 시리즈를 대상으로 TMDB에서 정확한 포스터를 검색하여 교체한다.

- poster_url: 세로 포스터 (w500)
- backdrop_url: 가로 포스터 (w1280) — 히어로 배너용

사용법:
    python scripts/fix_serving_posters.py              # dry-run
    python scripts/fix_serving_posters.py --apply       # 실제 DB 업데이트
    python scripts/fix_serving_posters.py --workers 20  # 병렬 수 조정
"""
import argparse
import io
import os
import re
import sys
import json
import urllib.request
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import psycopg2
from dotenv import load_dotenv

load_dotenv()

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_BASE = "https://image.tmdb.org/t/p/w1280"
EP_PATTERN = re.compile(r"\s*\d+회$|\s*시즌\d+$|\s*\d+기$")


def get_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def load_serving_series(conn) -> list[dict]:
    """서빙 테이블에 노출되는 고유 시리즈 목록 로드."""
    cur = conn.cursor()
    vod_ids: set[str] = set()

    tables = [
        "serving.tag_recommendation",
        "serving.tag_recommendation_test",
        "serving.hybrid_recommendation",
        "serving.hybrid_recommendation_test",
        "serving.popular_recommendation",
    ]
    for tbl in tables:
        cur.execute(f"SELECT DISTINCT vod_id_fk FROM {tbl}")
        for (vid,) in cur.fetchall():
            vod_ids.add(vid)
        print(f"  {tbl}: +{cur.rowcount} → 누적 {len(vod_ids)}")

    if not vod_ids:
        cur.close()
        return []

    cur.execute("""
        SELECT series_nm, ct_cl, poster_url, backdrop_url
        FROM public.vod
        WHERE full_asset_id = ANY(%s) AND poster_url IS NOT NULL
    """, (list(vod_ids),))

    seen = {}
    for series_nm, ct_cl, poster_url, backdrop_url in cur.fetchall():
        if series_nm not in seen:
            seen[series_nm] = {
                "series_nm": series_nm,
                "ct_cl": ct_cl or "",
                "poster_url": poster_url or "",
                "backdrop_url": backdrop_url or "",
            }
    cur.close()
    return list(seen.values())


def tmdb_search(query: str, ct_cl: str) -> dict | None:
    """TMDB에서 검색. ct_cl에 따라 movie/tv 순서 결정."""
    clean_query = EP_PATTERN.sub("", query).strip() or query
    is_movie = ct_cl in ("영화", "해외시리즈(영화)")
    search_order = ["movie", "tv"] if is_movie else ["tv", "movie"]

    for media_type in search_order:
        url = (
            f"https://api.themoviedb.org/3/search/{media_type}"
            f"?api_key={TMDB_API_KEY}"
            f"&query={urllib.parse.quote(clean_query)}"
            f"&language=ko-KR"
        )
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
        except Exception:
            continue

        if not data.get("results"):
            continue

        name_key = "title" if media_type == "movie" else "name"

        # 정확 매칭 우선
        for r in data["results"]:
            tmdb_name = r.get(name_key, "")
            if tmdb_name == clean_query or tmdb_name == query:
                return {
                    "tmdb_name": tmdb_name,
                    "media_type": media_type,
                    "poster_path": r.get("poster_path"),
                    "backdrop_path": r.get("backdrop_path"),
                }

        # 부분 매칭 (포함 관계)
        first = data["results"][0]
        tmdb_name = first.get(name_key, "")
        if clean_query in tmdb_name or tmdb_name in clean_query:
            return {
                "tmdb_name": tmdb_name,
                "media_type": media_type,
                "poster_path": first.get("poster_path"),
                "backdrop_path": first.get("backdrop_path"),
            }

    return None


def search_one(item: dict) -> dict:
    """단일 시리즈 TMDB 검색 (ThreadPool worker용)."""
    series_nm = item["series_nm"]
    ct_cl = item["ct_cl"]

    # 이미 TMDB URL이면 스킵
    if "tmdb.org" in item["poster_url"]:
        return {"series_nm": series_nm, "status": "skip_tmdb"}

    result = tmdb_search(series_nm, ct_cl)
    if not result:
        return {"series_nm": series_nm, "status": "no_match"}

    new_poster = f"{TMDB_POSTER_BASE}{result['poster_path']}" if result["poster_path"] else None
    new_backdrop = f"{TMDB_BACKDROP_BASE}{result['backdrop_path']}" if result["backdrop_path"] else None

    if not new_poster and not new_backdrop:
        return {"series_nm": series_nm, "status": "no_match"}

    return {
        "series_nm": series_nm,
        "status": "matched",
        "new_poster": new_poster,
        "new_backdrop": new_backdrop,
        "tmdb_name": result["tmdb_name"],
        "media_type": result["media_type"],
    }


def main():
    parser = argparse.ArgumentParser(description="서빙 포스터 TMDB 일괄 교체")
    parser.add_argument("--apply", action="store_true", help="실제 DB 업데이트")
    parser.add_argument("--workers", type=int, default=10, help="병렬 스레드 수 (기본 10)")
    args = parser.parse_args()

    if not TMDB_API_KEY:
        print("[ERROR] TMDB_API_KEY 없음")
        sys.exit(1)

    conn = get_connection()
    mode = "[APPLY]" if args.apply else "[DRY-RUN]"
    print(f"{'=' * 70}\n서빙 포스터 TMDB 일괄 교체 {mode} (workers={args.workers})\n{'=' * 70}")

    series_list = load_serving_series(conn)
    total = len(series_list)
    print(f"대상 시리즈: {total}개\n")

    # Phase 1: 병렬 TMDB 검색
    print(f"[Phase 1] TMDB 검색 (병렬 {args.workers} threads)...")
    results = []
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {executor.submit(search_one, s): s for s in series_list}
        for future in as_completed(futures):
            results.append(future.result())
            done += 1
            if done % 200 == 0:
                print(f"  검색 진행: {done}/{total}")

    # 집계
    skip_tmdb = [r for r in results if r["status"] == "skip_tmdb"]
    no_match = [r for r in results if r["status"] == "no_match"]
    matched = [r for r in results if r["status"] == "matched"]

    print(f"  완료: TMDB 매칭 {len(matched)}개 / 이미 TMDB {len(skip_tmdb)}개 / 매칭 실패 {len(no_match)}개\n")

    # Phase 2: DB 업데이트
    poster_cnt = sum(1 for r in matched if r.get("new_poster"))
    backdrop_cnt = sum(1 for r in matched if r.get("new_backdrop"))

    print(f"[Phase 2] DB 업데이트 대상: poster {poster_cnt}개 / backdrop {backdrop_cnt}개")
    for r in matched[:10]:
        p = "P" if r.get("new_poster") else "-"
        b = "B" if r.get("new_backdrop") else "-"
        print(f"  [{p}{b}] {r['series_nm']} ← TMDB:{r['tmdb_name']} ({r['media_type']})")
    if len(matched) > 10:
        print(f"  ... +{len(matched) - 10}개 더")

    updated_rows = 0
    errors = []
    BATCH = 500
    if args.apply and matched:
        print(f"\n  DB 반영 중 (배치 {BATCH}건씩)...")
        cur = conn.cursor()
        # poster + backdrop 동시 업데이트: temp table → JOIN UPDATE
        for batch_start in range(0, len(matched), BATCH):
            batch = matched[batch_start:batch_start + BATCH]
            # VALUES 리스트 구성: (series_nm, new_poster, new_backdrop)
            values = []
            params = []
            for r in batch:
                values.append("(%s, %s, %s)")
                params.extend([
                    r["series_nm"],
                    r.get("new_poster"),
                    r.get("new_backdrop"),
                ])
            try:
                cur.execute(f"""
                    UPDATE public.vod v
                    SET poster_url  = COALESCE(t.new_poster, v.poster_url),
                        backdrop_url = COALESCE(t.new_backdrop, v.backdrop_url)
                    FROM (VALUES {','.join(values)})
                        AS t(series_nm, new_poster, new_backdrop)
                    WHERE v.series_nm = t.series_nm
                """, params)
                updated_rows += cur.rowcount
                conn.commit()
                print(f"  배치 {batch_start+len(batch)}/{len(matched)} 완료 ({updated_rows} rows)")
            except Exception as e:
                errors.append((f"batch_{batch_start}", str(e)))
                conn.rollback()
        cur.close()

    conn.close()

    # 요약
    print(f"\n{'=' * 70}")
    print("결과 요약")
    print(f"{'=' * 70}")
    print(f"  전체 시리즈: {total}개")
    print(f"  이미 TMDB: {len(skip_tmdb)}개 (스킵)")
    print(f"  매칭 실패: {len(no_match)}개 (스킵)")
    print(f"  포스터(세로) 교체: {poster_cnt}개")
    print(f"  백드롭(가로) 교체: {backdrop_cnt}개")
    if args.apply:
        print(f"  DB 업데이트: {updated_rows} rows")
    else:
        print("  → --apply 플래그로 실행하면 실제 DB에 반영됩니다.")
    if errors:
        print(f"\n  오류 {len(errors)}건:")
        for nm, err in errors[:5]:
            print(f"    {nm}: {err}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
