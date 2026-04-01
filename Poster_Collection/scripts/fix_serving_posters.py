"""
fix_serving_posters.py — serving VOD의 poster_url + backdrop_url 일괄 수정

3단계 자동 실행:
  1단계: ct_cl 기반 TMDB 재검색으로 잘못 매칭된 poster/backdrop 교체
  2단계: 1단계 실패 시 기존 TMDB URL → OCI 마이그레이션
  3단계: poster/backdrop NULL인 VOD 신규 수집

처리 단위: (series_nm, ct_cl) 그룹
  - 같은 series_nm이라도 ct_cl이 다르면 별도 TMDB 검색
  - search/movie 또는 search/tv 엔드포인트 직접 호출 (search/multi 사용 안 함)
  - poster(w500) + backdrop(w1280) 동시 수집

Usage:
    python Poster_Collection/scripts/fix_serving_posters.py
    python Poster_Collection/scripts/fix_serving_posters.py --dry-run
    python Poster_Collection/scripts/fix_serving_posters.py --resume
    python Poster_Collection/scripts/fix_serving_posters.py --include-tag   # tag_recommendation 포함 (느림)
"""

import argparse
import json
import logging
import os
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

import psycopg2
import requests
from dotenv import load_dotenv

_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_root))

load_dotenv(_root / "RAG" / "config" / "api_keys.env")
load_dotenv(_root / ".env")

from Poster_Collection.src.oci_uploader import upload_file, object_exists, build_public_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── 설정 ────────────────────────────────────────────────────────────────────
TMDB_READ_ACCESS_TOKEN = os.getenv("TMDB_READ_ACCESS_TOKEN", "")
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "")
TMDB_URL = "https://api.themoviedb.org/3"
POSTER_IMG_BASE = "https://image.tmdb.org/t/p/w500"
BACKDROP_IMG_BASE = "https://image.tmdb.org/t/p/w1280"
REQUEST_TIMEOUT = 10
WORKERS = 8
BATCH_SIZE = 100
SIM_THRESHOLD = 0.5

_DATA_DIR = _root / "Poster_Collection" / "data"
_CHECKPOINT_FILE = _DATA_DIR / "fix_serving_checkpoint.json"

_CT_CL_MEDIA = {
    "영화":        "movie",
    "TV드라마":    "tv",
    "TV애니메이션": "tv",
    "키즈":        "tv",
    "TV 시사/교양": "tv",
    "TV 연예/오락": "tv",
    "공연/음악":   "movie",
    "다큐":        "tv",
    "교육":        "tv",
}

_thread_local = threading.local()
_lock = threading.Lock()


# ── DB ──────────────────────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"), port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


# ── TMDB ────────────────────────────────────────────────────────────────────
def _tmdb_headers():
    h = {"Accept": "application/json"}
    if TMDB_READ_ACCESS_TOKEN:
        h["Authorization"] = f"Bearer {TMDB_READ_ACCESS_TOKEN}"
    return h


def _tmdb_params(extra=None):
    p = {}
    if not TMDB_READ_ACCESS_TOKEN and TMDB_API_KEY:
        p["api_key"] = TMDB_API_KEY
    if extra:
        p.update(extra)
    return p


def _get_session():
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update(_tmdb_headers())
        _thread_local.session = s
    return _thread_local.session


def _title_sim(query, item):
    """query와 TMDB 결과의 제목 유사도.

    한국 콘텐츠(original_language=ko): 모든 제목 후보로 비교.
    비한국 콘텐츠: original_title/original_name으로만 비교하여
    한국어 번역 제목과의 오매칭 방지 (예: "샤이닝" ↛ "The Shining").
    """
    is_ko = item.get("original_language") == "ko"
    if is_ko:
        names = [item.get(k) or "" for k in ("title", "name", "original_title", "original_name")]
    else:
        names = [item.get(k) or "" for k in ("original_title", "original_name")]
    names = [n for n in names if n]
    if not names:
        return 0.0
    q = query.lower().strip()
    return max(SequenceMatcher(None, q, n.lower().strip()).ratio() for n in names)


def _best_title(item):
    return (item.get("title") or item.get("name")
            or item.get("original_title") or item.get("original_name") or "")


def search_tmdb(series_nm, ct_cl):
    """ct_cl 기반 TMDB 검색 → poster_path + backdrop_path 동시 반환.

    한국 콘텐츠 우선: original_language=ko 결과를 먼저 선택.
    비한국 결과는 원제(original_title)로만 유사도를 계산하여
    한국어 번역 제목으로 인한 오매칭을 방지.

    Returns:
        {"poster_path": str|None, "backdrop_path": str|None,
         "matched_title": str, "tmdb_id": int, "sim": float}
        or None
    """
    media_type = _CT_CL_MEDIA.get(ct_cl, "tv")
    endpoint = f"{TMDB_URL}/search/{'movie' if media_type == 'movie' else 'tv'}"
    session = _get_session()

    for lang in ("ko-KR", "en-US"):
        try:
            r = session.get(
                endpoint,
                params=_tmdb_params({"query": series_nm, "language": lang, "page": 1}),
                timeout=REQUEST_TIMEOUT,
            )
            if r.status_code == 429:
                time.sleep(5)
                continue
            if r.status_code != 200:
                continue
            results = r.json().get("results", [])
            if not results:
                continue

            scored = [(item, _title_sim(series_nm, item)) for item in results]
            scored = [(item, sim) for item, sim in scored if sim >= SIM_THRESHOLD]
            if not scored:
                continue

            # 한국 콘텐츠 우선 선택
            ko_results = [(item, sim) for item, sim in scored
                          if item.get("original_language") == "ko"]
            if ko_results:
                ko_results.sort(key=lambda x: x[1], reverse=True)
                best, sim = ko_results[0]
            else:
                scored.sort(key=lambda x: x[1], reverse=True)
                best, sim = scored[0]

            return {
                "poster_path": best.get("poster_path"),
                "backdrop_path": best.get("backdrop_path"),
                "matched_title": _best_title(best),
                "tmdb_id": best.get("id"),
                "sim": sim,
            }
        except Exception:
            continue
    return None


# ── OCI 업로드 ──────────────────────────────────────────────────────────────
def _download_and_upload(image_url, object_name):
    """이미지 URL → 다운로드 → OCI 업로드 → public URL 반환. 실패 시 None."""
    # 이미 OCI에 있으면 URL만 반환
    try:
        if object_exists(object_name):
            return build_public_url(
                os.getenv("OCI_REGION"), os.getenv("OCI_NAMESPACE"),
                os.getenv("OCI_BUCKET_NAME"), object_name,
            )
    except Exception:
        pass

    try:
        r = requests.get(image_url, timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
    except Exception:
        return None

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(r.content)
            tmp_path = f.name
        return upload_file(tmp_path, object_name)
    except Exception as e:
        log.warning("OCI 업로드 실패 %s: %s", object_name, e)
        return None
    finally:
        if tmp_path:
            Path(tmp_path).unlink(missing_ok=True)


# ── 그룹 처리 ───────────────────────────────────────────────────────────────
def process_group(row):
    """(series_nm, ct_cl, cur_poster, cur_backdrop) 1건 처리.

    1단계: TMDB 재검색 (ct_cl 기반) → poster + backdrop 동시 수집
    2단계: 재검색 실패 시 기존 TMDB URL → OCI 마이그레이션
    3단계: (1, 2 결과로 NULL → 신규 수집 자동 포함)
    """
    series_nm, ct_cl, cur_poster, cur_backdrop = row
    res = {
        "series_nm": series_nm, "ct_cl": ct_cl,
        "poster_url": None, "poster_action": "none",
        "backdrop_url": None, "backdrop_action": "none",
    }

    poster_obj = f"posters/{series_nm}__{ct_cl or 'unknown'}.jpg"
    backdrop_obj = f"backdrops/{series_nm}__{ct_cl or 'unknown'}.jpg"

    # ── 1단계: TMDB 재검색 ──
    tmdb = search_tmdb(series_nm, ct_cl or "")

    if tmdb and tmdb["poster_path"]:
        url = _download_and_upload(f"{POSTER_IMG_BASE}{tmdb['poster_path']}", poster_obj)
        if url:
            res["poster_url"] = url
            res["poster_action"] = "researched"

    if tmdb and tmdb["backdrop_path"]:
        url = _download_and_upload(f"{BACKDROP_IMG_BASE}{tmdb['backdrop_path']}", backdrop_obj)
        if url:
            res["backdrop_url"] = url
            res["backdrop_action"] = "researched"

    # ── 2단계: TMDB URL → OCI 마이그레이션 (1단계 실패 시) ──
    if not res["poster_url"] and cur_poster and "tmdb.org" in cur_poster:
        url = _download_and_upload(cur_poster, poster_obj)
        if url:
            res["poster_url"] = url
            res["poster_action"] = "migrated"

    if not res["backdrop_url"] and cur_backdrop and "tmdb.org" in cur_backdrop:
        url = _download_and_upload(cur_backdrop, backdrop_obj)
        if url:
            res["backdrop_url"] = url
            res["backdrop_action"] = "migrated"

    # ── 기존 OCI URL 유지 (1, 2 모두 실패) ──
    if not res["poster_url"] and cur_poster and "objectstorage" in cur_poster:
        res["poster_url"] = cur_poster
        res["poster_action"] = "kept"

    if not res["backdrop_url"] and cur_backdrop and "objectstorage" in cur_backdrop:
        res["backdrop_url"] = cur_backdrop
        res["backdrop_action"] = "kept"

    return res


# ── 메인 ────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="serving VOD poster/backdrop 일괄 수정")
    parser.add_argument("--dry-run", action="store_true", help="DB 미반영, 검색+업로드만")
    parser.add_argument("--resume", action="store_true", help="체크포인트에서 재개")
    parser.add_argument("--workers", type=int, default=WORKERS, help="병렬 워커 수")
    parser.add_argument("--include-tag", action="store_true",
                        help="tag_recommendation 포함 (16M행, 쿼리 매우 느림)")
    args = parser.parse_args()

    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    # ── Step 1: 대상 (series_nm, ct_cl) 그룹 조회 ──
    tag_union = "UNION SELECT vod_id_fk FROM serving.tag_recommendation" if args.include_tag else ""
    log.info("[1/4] serving VOD (series_nm, ct_cl) 그룹 조회 중... (5~10분 소요)")
    t0 = time.time()
    conn = get_conn()
    with conn.cursor() as cur:
        cur.execute(f"""
            SELECT v.series_nm, v.ct_cl,
                   MAX(v.poster_url) AS cur_poster,
                   MAX(v.backdrop_url) AS cur_backdrop
            FROM public.vod v
            WHERE v.series_nm IS NOT NULL
              AND v.full_asset_id IN (
                SELECT vod_id_fk FROM serving.popular_recommendation
                UNION
                SELECT vod_id_fk FROM serving.hybrid_recommendation
                {tag_union}
              )
            GROUP BY v.series_nm, v.ct_cl
            ORDER BY v.series_nm, v.ct_cl
        """)
        all_groups = cur.fetchall()
    conn.close()
    log.info("  → %d개 그룹 조회 완료 (%.1f초)", len(all_groups), time.time() - t0)

    # resume: 이미 처리한 그룹 스킵
    processed_keys = set()
    all_results = []
    if args.resume and _CHECKPOINT_FILE.exists():
        with open(_CHECKPOINT_FILE, encoding="utf-8") as f:
            data = json.load(f)
        processed_keys = {tuple(k) for k in data.get("processed_keys", [])}
        all_results = data.get("results", [])
        before = len(all_groups)
        all_groups = [g for g in all_groups if (g[0], g[1]) not in processed_keys]
        log.info("  → 재개: %d건 처리 완료, %d건 남음", before - len(all_groups), len(all_groups))

    if not all_groups:
        log.info("처리할 그룹 없음")
        if all_results:
            log.info("이전 결과로 DB 업데이트 진행")
        else:
            return

    # ── Step 2: TMDB 재검색 + OCI 업로드 (병렬) ──
    if all_groups:
        log.info("[2/4] TMDB 재검색 + OCI 업로드 (%d workers, %d groups)...", args.workers, len(all_groups))
        stats = {"researched": 0, "migrated": 0, "kept": 0, "none": 0}
        processed = 0

        with ThreadPoolExecutor(max_workers=args.workers) as exe:
            futures = {exe.submit(process_group, g): g for g in all_groups}
            for fut in as_completed(futures):
                res = fut.result()
                all_results.append(res)
                with _lock:
                    for action_key in ("poster_action", "backdrop_action"):
                        a = res[action_key]
                        if a in stats:
                            stats[a] += 1
                    processed_keys.add((res["series_nm"], res["ct_cl"]))
                    processed += 1

                    if processed % 50 == 0:
                        _save_checkpoint(processed_keys, all_results, stats)
                        log.info("  진행 %d/%d | 재검색=%d 마이그레이션=%d 유지=%d 실패=%d",
                                 processed, len(all_groups),
                                 stats["researched"], stats["migrated"],
                                 stats["kept"], stats["none"])

        _save_checkpoint(processed_keys, all_results, stats, completed=True)
        log.info("[3/4] 완료: 재검색=%d, 마이그레이션=%d, 유지=%d, 미매칭=%d",
                 stats["researched"], stats["migrated"], stats["kept"], stats["none"])

    # ── Step 3: DB 배치 UPDATE ──
    # poster_action 또는 backdrop_action이 "researched"/"migrated"인 것만 UPDATE
    update_rows = [
        r for r in all_results
        if r.get("poster_action") in ("researched", "migrated")
        or r.get("backdrop_action") in ("researched", "migrated")
    ]

    if not update_rows:
        log.info("DB 업데이트 대상 없음")
        return

    if args.dry_run:
        log.info("[DRY-RUN] DB 업데이트 대상 %d건 — 샘플:", len(update_rows))
        for r in update_rows[:10]:
            log.info("  %s / %s → poster:%s backdrop:%s",
                     r["series_nm"], r["ct_cl"], r["poster_action"], r["backdrop_action"])
        return

    log.info("[4/4] DB 배치 UPDATE (%d건)...", len(update_rows))
    conn = get_conn()
    total_updated = 0
    try:
        for i in range(0, len(update_rows), BATCH_SIZE):
            batch = update_rows[i:i + BATCH_SIZE]
            with conn.cursor() as cur:
                for r in batch:
                    sets = []
                    params = []
                    if r["poster_url"] and r["poster_action"] not in ("kept", "none"):
                        sets.append("poster_url = %s")
                        params.append(r["poster_url"])
                    if r["backdrop_url"] and r["backdrop_action"] not in ("kept", "none"):
                        sets.append("backdrop_url = %s")
                        params.append(r["backdrop_url"])
                    if not sets:
                        continue
                    sets.append("updated_at = NOW()")
                    params.extend([r["series_nm"], r["ct_cl"]])
                    cur.execute(
                        f"UPDATE public.vod SET {', '.join(sets)} "
                        f"WHERE series_nm = %s AND ct_cl = %s",
                        params,
                    )
                    total_updated += cur.rowcount
            conn.commit()
            log.info("  UPDATE 진행 %d/%d 그룹", min(i + BATCH_SIZE, len(update_rows)), len(update_rows))
    finally:
        conn.close()

    log.info("완료: %d행 poster_url/backdrop_url 업데이트", total_updated)


def _save_checkpoint(processed_keys, results, stats, completed=False):
    with open(_CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "processed_keys": [list(k) for k in processed_keys],
            "results": results,
            "stats": stats,
            "completed": completed,
            "updated_at": datetime.now().isoformat(),
        }, f, ensure_ascii=False)


if __name__ == "__main__":
    main()
