"""TMDB backdrop(가로 포스터) 크롤링 → OCI 업로드 → vod.backdrop_url UPDATE.

처리 단위: (series_nm, ct_cl) 그룹
  - 같은 series_nm이라도 ct_cl(영화/TV드라마 등)이 다르면 별도 콘텐츠로 취급
  - TMDB 검색은 series_nm으로 수행 (asset_nm에 에피소드 번호 포함 문제 방지)
  - OCI 키: backdrops/{url_encoded_series_nm}__{url_encoded_ct_cl}.jpg
  - UPDATE: 같은 (series_nm, ct_cl)을 가진 전체 VOD에 동일 backdrop_url 적용

DB 왕복 계획:
  읽기: serving 테이블 UNION (1회) → (series_nm, ct_cl) DISTINCT
  쓰기: UPDATE 배치 (100행 단위)

Usage:
    python Poster_Collection/scripts/crawl_backdrops.py
    python Poster_Collection/scripts/crawl_backdrops.py --dry-run      # DB 미반영
    python Poster_Collection/scripts/crawl_backdrops.py --all-vods     # 전체 vod 대상
    python Poster_Collection/scripts/crawl_backdrops.py --overwrite    # 기존 backdrop_url도 덮어씀
"""

import argparse
import logging
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

sys.path.insert(0, ".")
from Poster_Collection.src.oci_uploader import upload_file, object_exists

load_dotenv("RAG/config/api_keys.env")
load_dotenv(".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN", "")
TMDB_API_KEY           = os.getenv("TMDB_API_KEY", "")
TMDB_URL               = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE        = "https://image.tmdb.org/t/p/w1280"
REQUEST_TIMEOUT        = 10
WORKERS                = 8
BATCH_SIZE             = 100
SLEEP_ON_429           = 5.0

_lock = threading.Lock()
_thread_local = threading.local()

# ct_cl → TMDB media_type 힌트
_CT_CL_MEDIA = {
    "영화":        "movie",
    "TV드라마":    "tv",
    "TV애니메이션": "tv",
    "키즈":        "tv",
    "TV 시사/교양": "tv",
    "공연/음악":   "movie",
    "다큐":        "tv",
    "교육":        "tv",
}


def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def _tmdb_headers() -> dict:
    h = {"Accept": "application/json"}
    if TMDB_READ_ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {TMDB_READ_ACCESS_TOKEN}"
    return h


def _tmdb_params(extra: dict = None) -> dict:
    p = {"language": "ko-KR"}
    if not TMDB_READ_ACCESS_TOKEN and TMDB_API_KEY:
        p["api_key"] = TMDB_API_KEY
    if extra:
        p.update(extra)
    return p


def _get_session() -> requests.Session:
    """Thread-local requests.Session (TCP 연결 재사용)."""
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update(_tmdb_headers())
        _thread_local.session = s
    return _thread_local.session


def _oci_object_name(series_nm: str, ct_cl: str) -> str:
    """(series_nm, ct_cl) → OCI object name (raw, 인코딩 없음 — build_public_url이 처리)."""
    return f"backdrops/{series_nm}__{ct_cl or 'unknown'}.jpg"


def _item_best_title(item: dict) -> str:
    """TMDB 결과 아이템에서 가장 대표적인 제목 반환."""
    return (item.get("title") or item.get("name")
            or item.get("original_title") or item.get("original_name") or "")


def _title_similarity(query: str, item: dict) -> float:
    """query와 TMDB 결과 아이템의 제목 유사도 (최대값)."""
    candidates = [
        item.get("title") or "",
        item.get("name") or "",
        item.get("original_title") or "",
        item.get("original_name") or "",
    ]
    candidates = [c for c in candidates if c]
    if not candidates:
        return 0.0
    q = query.lower().strip()
    return max(SequenceMatcher(None, q, c.lower().strip()).ratio() for c in candidates)


def fetch_backdrop_path(series_nm: str, ct_cl: str) -> str | None:
    """TMDB 검색 → backdrop_path 반환. 실패 시 None.

    ct_cl에 따라 search/movie 또는 search/tv 엔드포인트를 직접 호출하여
    다른 media_type 결과가 섞이는 문제를 방지.
    한국어(ko-KR) → 영어(en-US) 순으로 검색하며, 제목 유사도 0.5 이상인
    결과 중 가장 유사도가 높은 항목을 선택.
    """
    media_type = _CT_CL_MEDIA.get(ct_cl, "tv")
    endpoint = f"{TMDB_URL}/search/{'movie' if media_type == 'movie' else 'tv'}"
    session = _get_session()

    for lang in ("ko-KR", "en-US"):
        for query in [series_nm, series_nm.split()[0] if " " in series_nm else None]:
            if not query:
                continue
            try:
                r = session.get(
                    endpoint,
                    params=_tmdb_params({"query": query, "language": lang, "page": 1}),
                    timeout=REQUEST_TIMEOUT,
                )
                if r.status_code == 429:
                    time.sleep(SLEEP_ON_429)
                    continue
                if r.status_code != 200:
                    continue
                results = r.json().get("results", [])
                if not results:
                    continue

                # 유사도 기준 정렬, 0.5 미만 제외
                scored = [(item, _title_similarity(query, item)) for item in results]
                scored = [(item, sim) for item, sim in scored if sim >= 0.5]
                if not scored:
                    continue
                scored.sort(key=lambda x: x[1], reverse=True)
                candidate, best_sim = scored[0]

                bp = candidate.get("backdrop_path")
                if bp:
                    matched = _item_best_title(candidate)
                    log.debug("backdrop 매칭: '%s' → '%s' (sim=%.2f, lang=%s)",
                              query, matched, best_sim, lang)
                    return bp
            except Exception:
                continue
    return None


def download_image(url: str) -> bytes | None:
    """이미지 URL → bytes. 실패 시 None."""
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT)
        if r.status_code == 200:
            return r.content
    except Exception:
        pass
    return None


def process_series(row: tuple) -> dict:
    """(series_nm, ct_cl) 처리: TMDB 검색 → 이미지 다운로드 → OCI 업로드."""
    series_nm, ct_cl = row

    backdrop_path = fetch_backdrop_path(series_nm, ct_cl or "")
    if not backdrop_path:
        return {"series_nm": series_nm, "ct_cl": ct_cl, "status": "no_backdrop"}

    object_name = _oci_object_name(series_nm, ct_cl)

    # OCI에 이미 있으면 URL만 반환
    try:
        if object_exists(object_name):
            from Poster_Collection.src.oci_uploader import build_public_url
            url = build_public_url(
                os.getenv("OCI_REGION"), os.getenv("OCI_NAMESPACE"),
                os.getenv("OCI_BUCKET_NAME"), object_name,
            )
            return {"series_nm": series_nm, "ct_cl": ct_cl, "status": "cached", "url": url}
    except Exception:
        pass  # OCI 연결 실패 시 재업로드

    image_url = f"{TMDB_IMAGE_BASE}{backdrop_path}"
    data = download_image(image_url)
    if not data:
        return {"series_nm": series_nm, "ct_cl": ct_cl, "status": "download_fail"}

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(data)
            tmp_path = f.name

        oci_url = upload_file(tmp_path, object_name)
        Path(tmp_path).unlink(missing_ok=True)
        return {"series_nm": series_nm, "ct_cl": ct_cl, "status": "uploaded", "url": oci_url}
    except Exception as e:
        log.warning("OCI 업로드 실패 (%s / %s): %s", series_nm, ct_cl, e)
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)
        return {"series_nm": series_nm, "ct_cl": ct_cl, "status": "upload_fail"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",   action="store_true", help="DB 미반영")
    parser.add_argument("--all-vods",  action="store_true", help="전체 vod 대상 (기본: 배너 serving 테이블만)")
    parser.add_argument("--overwrite", action="store_true", help="기존 backdrop_url도 덮어씀 (잘못 수집된 것 재수집)")
    parser.add_argument("--workers",   type=int, default=WORKERS)
    args = parser.parse_args()

    # ── Step 1: 대상 (series_nm, ct_cl) 조회 ────────────────────────────────
    log.info("[1/3] 대상 시리즈 조회...")
    null_cond = "" if args.overwrite else "AND v.backdrop_url IS NULL"
    conn = get_conn()
    with conn.cursor() as cur:
        if args.all_vods:
            cur.execute(f"""
                SELECT DISTINCT series_nm, ct_cl
                FROM public.vod
                WHERE series_nm IS NOT NULL
                  {null_cond}
                ORDER BY series_nm, ct_cl
            """)
        else:
            cur.execute(f"""
                SELECT DISTINCT v.series_nm, v.ct_cl
                FROM public.vod v
                WHERE v.series_nm IS NOT NULL
                  {null_cond}
                  AND v.full_asset_id IN (
                    SELECT vod_id_fk FROM serving.popular_recommendation
                    UNION
                    SELECT vod_id_fk FROM serving.hybrid_recommendation
                  )
                ORDER BY v.series_nm, v.ct_cl
            """)
        all_series = cur.fetchall()
    conn.close()
    log.info("  → 처리 대상: %d개 (series_nm, ct_cl) 그룹", len(all_series))

    if not all_series:
        log.info("처리할 시리즈 없음")
        return

    # ── Step 2: 병렬 처리 ───────────────────────────────────────────────────
    log.info("[2/3] TMDB 검색 + OCI 업로드 (%d workers)...", args.workers)
    # results: {(series_nm, ct_cl): url}
    results: dict[tuple, str] = {}
    processed = 0
    total = len(all_series)
    stats = {"uploaded": 0, "cached": 0, "no_backdrop": 0, "fail": 0}

    with ThreadPoolExecutor(max_workers=args.workers) as exe:
        futures = {exe.submit(process_series, row): row for row in all_series}
        for fut in as_completed(futures):
            res = fut.result()
            with _lock:
                status = res["status"]
                key = (res["series_nm"], res["ct_cl"])
                if status in ("uploaded", "cached"):
                    results[key] = res["url"]
                    stats[status] += 1
                elif status == "no_backdrop":
                    stats["no_backdrop"] += 1
                else:
                    stats["fail"] += 1
                processed += 1
                if processed % 50 == 0:
                    log.info("  진행: %d/%d (업로드 %d, 캐시 %d, 미매칭 %d, 실패 %d)",
                             processed, total,
                             stats["uploaded"], stats["cached"],
                             stats["no_backdrop"], stats["fail"])

    log.info("  → 결과: 업로드 %d, 캐시 %d, TMDB미매칭 %d, 실패 %d",
             stats["uploaded"], stats["cached"], stats["no_backdrop"], stats["fail"])

    if args.dry_run:
        log.info("[DRY-RUN] 샘플 5건:")
        for (snm, ct), url in list(results.items())[:5]:
            log.info("  (%s / %s) → %s", snm, ct, url)
        return

    # ── Step 3: 배치 UPDATE ─────────────────────────────────────────────────
    log.info("[3/3] vod.backdrop_url 배치 UPDATE (series_nm + ct_cl 단위)...")
    rows = list(results.items())
    total_updated = 0
    overwrite_cond = "" if args.overwrite else "AND v.backdrop_url IS NULL"
    conn = get_conn()
    try:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            with conn.cursor() as cur:
                args_str = ",".join(
                    cur.mogrify("(%s,%s,%s)", (url, snm, ct)).decode()
                    for (snm, ct), url in batch
                )
                cur.execute(f"""
                    UPDATE public.vod AS v
                    SET backdrop_url = c.backdrop_url,
                        updated_at   = NOW()
                    FROM (VALUES {args_str}) AS c(backdrop_url, series_nm, ct_cl)
                    WHERE v.series_nm = c.series_nm
                      AND v.ct_cl    = c.ct_cl
                      {overwrite_cond}
                """)
                total_updated += cur.rowcount
            conn.commit()
            log.info("  UPDATE 진행: %d/%d", min(i + BATCH_SIZE, len(rows)), len(rows))
    finally:
        conn.close()

    log.info("완료: %d건 backdrop_url 업데이트", total_updated)


if __name__ == "__main__":
    main()
