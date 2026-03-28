"""TMDB backdrop(가로 포스터) 크롤링 → OCI 업로드 → vod.backdrop_url UPDATE.

대상: 히어로 배너 serving 테이블에 있는 unique VOD
방법: TMDB search/multi → backdrop_path → w1280 이미지 다운로드 → OCI → DB UPDATE

DB 왕복 계획:
  읽기: serving 테이블 UNION (1회)
  쓰기: UPDATE 배치 (100행 단위)

Usage:
    python Poster_Collection/scripts/crawl_backdrops.py
    python Poster_Collection/scripts/crawl_backdrops.py --dry-run   # DB 미반영
    python Poster_Collection/scripts/crawl_backdrops.py --all-vods  # 전체 vod 대상
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


def fetch_backdrop_path(asset_nm: str, ct_cl: str) -> str | None:
    """TMDB 검색 → backdrop_path 반환. 실패 시 None."""
    prefer_movie = _CT_CL_MEDIA.get(ct_cl, "tv") == "movie"
    session = _get_session()

    for query in [asset_nm, asset_nm.split()[0] if " " in asset_nm else None]:
        if not query:
            continue
        try:
            r = session.get(
                f"{TMDB_URL}/search/multi",
                params=_tmdb_params({"query": query, "page": 1}),
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

            preferred = [x for x in results if x.get("media_type") == ("movie" if prefer_movie else "tv")]
            candidate = preferred[0] if preferred else None
            if not candidate:
                continue

            matched_title = candidate.get("title") or candidate.get("name") or ""
            sim = SequenceMatcher(None, query.lower(), matched_title.lower()).ratio()
            if sim < 0.4:
                continue

            bp = candidate.get("backdrop_path")
            if bp:
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


def process_vod(row: tuple) -> dict:
    """단일 VOD 처리: TMDB 검색 → 이미지 다운로드 → OCI 업로드."""
    full_asset_id, asset_nm, ct_cl = row

    backdrop_path = fetch_backdrop_path(asset_nm, ct_cl or "")
    if not backdrop_path:
        return {"vod_id": full_asset_id, "status": "no_backdrop"}

    object_name = f"backdrops/{full_asset_id}.jpg"

    # OCI에 이미 있으면 URL만 반환
    try:
        if object_exists(object_name):
            namespace = os.getenv("OCI_NAMESPACE")
            bucket    = os.getenv("OCI_BUCKET_NAME")
            region    = os.getenv("OCI_REGION")
            from Poster_Collection.src.oci_uploader import build_public_url
            url = build_public_url(region, namespace, bucket, object_name)
            return {"vod_id": full_asset_id, "status": "cached", "url": url}
    except Exception:
        pass  # OCI 연결 실패 시 재업로드

    image_url = f"{TMDB_IMAGE_BASE}{backdrop_path}"
    data = download_image(image_url)
    if not data:
        return {"vod_id": full_asset_id, "status": "download_fail"}

    # 임시 파일에 저장 후 OCI 업로드
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(data)
            tmp_path = f.name

        oci_url = upload_file(tmp_path, object_name)
        Path(tmp_path).unlink(missing_ok=True)
        return {"vod_id": full_asset_id, "status": "uploaded", "url": oci_url}
    except Exception as e:
        log.warning("OCI 업로드 실패 %s: %s", full_asset_id, e)
        Path(tmp_path).unlink(missing_ok=True)
        return {"vod_id": full_asset_id, "status": "upload_fail"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="DB 미반영")
    parser.add_argument("--all-vods", action="store_true", help="전체 vod 대상 (기본: 배너 serving 테이블만)")
    parser.add_argument("--workers",  type=int, default=WORKERS)
    args = parser.parse_args()

    # ── Step 1: 대상 VOD 조회 ────────────────────────────────────────────────
    log.info("[1/3] 대상 VOD 조회...")
    conn = get_conn()
    with conn.cursor() as cur:
        if args.all_vods:
            cur.execute("""
                SELECT full_asset_id, asset_nm, ct_cl
                FROM public.vod
                WHERE backdrop_url IS NULL
                ORDER BY full_asset_id
            """)
        else:
            # 히어로 배너 serving 테이블 UNION → backdrop_url 미설정 VOD만
            cur.execute("""
                SELECT DISTINCT v.full_asset_id, v.asset_nm, v.ct_cl
                FROM public.vod v
                WHERE v.backdrop_url IS NULL
                  AND v.full_asset_id IN (
                    SELECT vod_id_fk FROM serving.popular_recommendation
                    UNION
                    SELECT vod_id_fk FROM serving.hybrid_recommendation
                  )
                ORDER BY v.full_asset_id
            """)
        all_vods = cur.fetchall()
    conn.close()
    log.info("  → 처리 대상: %d건", len(all_vods))

    if not all_vods:
        log.info("처리할 VOD 없음 (이미 모두 backdrop_url 설정됨)")
        return

    # ── Step 2: 병렬 처리 ───────────────────────────────────────────────────
    log.info("[2/3] TMDB 검색 + OCI 업로드 (%d workers)...", args.workers)
    results = {}   # {vod_id: url}
    processed = 0
    total = len(all_vods)
    stats = {"uploaded": 0, "cached": 0, "no_backdrop": 0, "fail": 0}

    with ThreadPoolExecutor(max_workers=args.workers) as exe:
        futures = {exe.submit(process_vod, row): row for row in all_vods}
        for fut in as_completed(futures):
            res = fut.result()
            with _lock:
                status = res["status"]
                if status in ("uploaded", "cached"):
                    results[res["vod_id"]] = res["url"]
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
        for vod_id, url in list(results.items())[:5]:
            log.info("  %s → %s", vod_id, url)
        return

    # ── Step 3: 배치 UPDATE ─────────────────────────────────────────────────
    log.info("[3/3] vod.backdrop_url 배치 UPDATE...")
    rows = list(results.items())
    total_updated = 0
    conn = get_conn()
    try:
        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i:i + BATCH_SIZE]
            with conn.cursor() as cur:
                args_str = ",".join(
                    cur.mogrify("(%s,%s)", (url, vod_id)).decode()
                    for vod_id, url in batch
                )
                cur.execute(f"""
                    UPDATE public.vod AS v
                    SET backdrop_url = c.backdrop_url,
                        updated_at   = NOW()
                    FROM (VALUES {args_str}) AS c(backdrop_url, full_asset_id)
                    WHERE v.full_asset_id = c.full_asset_id
                """)
                total_updated += cur.rowcount
            conn.commit()
            log.info("  UPDATE 진행: %d/%d", min(i + BATCH_SIZE, len(rows)), len(rows))
    finally:
        conn.close()

    log.info("완료: %d건 backdrop_url 업데이트", total_updated)


if __name__ == "__main__":
    main()
