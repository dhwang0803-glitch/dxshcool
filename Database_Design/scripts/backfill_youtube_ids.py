"""
에피소드별 YouTube video ID 일괄 검색 → vod.youtube_video_id 적재

기존 crawl_trailers.py는 시리즈 대표 1개만 검색했으나,
이 스크립트는 모든 VOD를 asset_nm(에피소드명) 기준으로 개별 검색한다.
다운로드 없이 메타데이터만 수집하므로 빠르다.

실행:
    conda activate myenv
    python Database_Design/scripts/backfill_youtube_ids.py                    # 전체 실행 (8 workers)
    python Database_Design/scripts/backfill_youtube_ids.py --workers 3        # 워커 수 조정
    python Database_Design/scripts/backfill_youtube_ids.py --limit 100        # 테스트
    python Database_Design/scripts/backfill_youtube_ids.py --ct-cl 영화       # 특정 ct_cl만
    python Database_Design/scripts/backfill_youtube_ids.py --status           # 진행 현황
    python Database_Design/scripts/backfill_youtube_ids.py --overwrite        # 기존 값 덮어쓰기
"""

import sys
import os
import json
import re
import time
import random
import argparse
import logging
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DB_ENV_PATH = PROJECT_ROOT / ".env"
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
STATUS_FILE = DATA_DIR / "yt_backfill_status.json"

BATCH_COMMIT = 200          # N건마다 DB COMMIT + 상태 저장
REQUEST_DELAY_MIN = 0.3     # 워커당 최소 대기 (초) — 쿠키 인증 시 축소 가능
REQUEST_DELAY_MAX = 0.8     # 워커당 최대 대기 (초)
MAX_RESULTS = 5             # 후보 늘려서 본편 잡을 확률 향상

# ct_cl별 duration 범위
# 본편 대상 (3분 이상): TV드라마, TV 연예/오락 — 에피소드 전체 영상 선별
EPISODE_CT_CL = {"TV드라마", "TV 연예/오락"}
EPISODE_DURATION_MIN = 180   # 3분 이상
EPISODE_DURATION_MAX = 1800  # 30분

# 트레일러 대상 (3분 이하): 그 외 ct_cl — 예고편/티저 선별
TRAILER_DURATION_MIN = 30    # 30초 이상
TRAILER_DURATION_MAX = 180   # 3분 이하

EXCLUDE_CT_CL = {"우리동네", "미분류"}

PROVIDER_KEYWORD = {
    "KBS": "KBS", "MBC": "MBC", "SBS": "SBS",
    "JTBC": "JTBC", "CJ ENM": "tvN", "EBS": "EBS",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "yt_backfill.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ── DB helpers ──────────────────────────────────────────────────────

def load_env():
    env = {}
    for p in [DB_ENV_PATH, PROJECT_ROOT / "Database_Design" / ".env"]:
        if p.exists():
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env[k.strip()] = v.strip()
            break
    return env


def get_db_conn():
    import psycopg2
    env = load_env()
    return psycopg2.connect(
        host=env.get("DB_HOST"),
        port=env.get("DB_PORT", 5432),
        dbname=env.get("DB_NAME"),
        user=env.get("DB_USER"),
        password=env.get("DB_PASSWORD"),
    )


# ── YouTube 검색 ───────────────────────────────────────────────────

def normalize_title(name: str) -> str:
    name = re.sub(r"(\d)([가-힣])", r"\1 \2", name)
    name = re.sub(r"([가-힣])(\d)", r"\1 \2", name)
    name = re.sub(r"([A-Za-z])([가-힣])", r"\1 \2", name)
    name = re.sub(r"([가-힣])([A-Za-z])", r"\1 \2", name)
    name = re.sub(r"\s*-\s*", " ", name)
    name = re.sub(r" {2,}", " ", name)
    return name.strip()


def build_queries(asset_nm: str, ct_cl: str, provider: str = None) -> list:
    """에피소드명(asset_nm) 기준 검색 쿼리 생성."""
    norm = normalize_title(asset_nm)
    bc = PROVIDER_KEYWORD.get(provider, "") if provider else ""

    queries = []
    if bc:
        queries.append(f"{norm} {bc}")
    queries.append(norm)

    if ct_cl == "영화":
        queries.append(f"{norm} 예고편")
    elif ct_cl in ("TV드라마", "TV 시사/교양", "TV 연예/오락"):
        # 회차 정보 포함 시 방송사+제목+회차로 검색
        ep_match = re.search(r"(\d{1,4})\s*[회화]", asset_nm)
        if ep_match and bc:
            queries.insert(0, f"{bc} {norm}")

    # 중복 제거 (순서 유지)
    seen = set()
    return [q for q in queries if not (q in seen or seen.add(q))]


def search_youtube(vod_id: str, asset_nm: str, ct_cl: str,
                   provider: str = None, cookies_file: str = None) -> dict:
    """
    YouTube 메타데이터만 검색 (다운로드 없음).
    ct_cl에 따라 duration 범위를 다르게 적용:
      - TV드라마 / TV 연예/오락 : 3분 이상 본편 선별 (최장 우선)
      - 그 외               : 30초~3분 트레일러/예고편 선별 (최장 우선)
    cookies_file: Netscape 형식 쿠키 파일 경로 (403 우회용, 없으면 비인증)
    반환: {"status": "success", "youtube_video_id": ..., "duration_sec": ...}
          또는 {"status": "failed", "reason": ...}
    """
    try:
        import yt_dlp
    except ImportError:
        return {"status": "error", "reason": "yt_dlp_not_installed"}

    is_episode = ct_cl in EPISODE_CT_CL
    dur_min = EPISODE_DURATION_MIN if is_episode else TRAILER_DURATION_MIN
    dur_max = EPISODE_DURATION_MAX if is_episode else TRAILER_DURATION_MAX

    queries = build_queries(asset_nm, ct_cl, provider)

    meta_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "extract_flat": True,
        "default_search": f"ytsearch{MAX_RESULTS}",
        "noplaylist": True,
        "socket_timeout": 20,
    }
    if cookies_file:
        meta_opts["cookiefile"] = cookies_file

    for query in queries:
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

        try:
            with yt_dlp.YoutubeDL(meta_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{MAX_RESULTS}:{query}", download=False)
            entries = info.get("entries", []) if info else []
        except Exception as e:
            err = str(e)
            if "429" in err or "Too Many Requests" in err:
                log.warning("YouTube 429 -- 60s wait")
                time.sleep(60)
            continue

        # ct_cl별 duration 범위 내 후보 선별
        valid = [
            e for e in entries
            if e and dur_min <= (e.get("duration") or 0) <= dur_max
        ]
        if not valid:
            continue

        # 최장 우선 — 본편/하이라이트가 Object Detection에 유리
        best = max(valid, key=lambda e: e.get("duration") or 0)
        return {
            "status": "success",
            "youtube_video_id": best.get("id", ""),
            "duration_sec": best.get("duration", 0),
            "query_used": query,
            "title": best.get("title", ""),
        }

    return {"status": "failed", "reason": "no_result", "queries": queries}


# ── 상태 관리 ──────────────────────────────────────────────────────

def load_status() -> dict:
    if STATUS_FILE.exists():
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"processed": {}, "last_updated": None, "stats": {"success": 0, "failed": 0}}


def save_status(status: dict):
    status["last_updated"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def print_status(status: dict):
    s = status.get("stats", {})
    total = s.get("success", 0) + s.get("failed", 0)
    print(f"\n=== YouTube ID Backfill ===")
    print(f"  success: {s.get('success', 0):,}")
    print(f"  failed:  {s.get('failed', 0):,}")
    print(f"  total:   {total:,}")
    print(f"  last:    {status.get('last_updated', 'N/A')}\n")


# ── 메인 ───────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="에피소드별 YouTube ID 일괄 검색")
    parser.add_argument("--workers", type=int, default=8, help="병렬 워커 수 (기본: 8)")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 제한")
    parser.add_argument("--ct-cl", nargs="+", help="특정 ct_cl만 처리")
    parser.add_argument("--status", action="store_true", help="진행 현황만 출력")
    parser.add_argument("--overwrite", action="store_true",
                        help="기존 youtube_video_id가 있어도 덮어쓰기")
    parser.add_argument("--reset", action="store_true",
                        help="상태 파일 초기화 후 처음부터 시작")
    parser.add_argument("--retry-failed", action="store_true",
                        help="이전에 failed 처리된 항목만 재시도")
    parser.add_argument("--partial-series-only", action="store_true",
                        help="동일 시리즈 내 성공한 에피소드가 1건 이상 있는 VOD만 처리")
    parser.add_argument("--cookies", type=str, default="",
                        metavar="COOKIES_FILE",
                        help="Netscape 형식 쿠키 파일 경로 (YouTube 403 우회용). "
                             "예: Database_Design/data/youtube_cookies.txt")
    args = parser.parse_args()

    cookies_file = None
    if args.cookies:
        cp = Path(args.cookies)
        if not cp.exists():
            log.warning(f"쿠키 파일 없음: {args.cookies} — 비인증 모드로 실행")
        else:
            # Windows CRLF → LF 정규화 (yt-dlp가 CRLF를 거부하는 문제 방지)
            raw = cp.read_bytes()
            normalized = raw.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
            norm_path = DATA_DIR / "_cookies_normalized.txt"
            norm_path.write_bytes(normalized)
            cookies_file = str(norm_path)
            log.info(f"쿠키 파일 로드: {cp.name} ({len(normalized):,} bytes)")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.reset and STATUS_FILE.exists():
        STATUS_FILE.unlink()
        log.info("Status file reset")

    status = load_status()

    if args.status:
        print_status(status)
        return

    # ── VOD 목록 로드 ─────────────────────────────────────────────
    conn = get_db_conn()
    cur = conn.cursor()

    where_clauses = ["ct_cl NOT IN %s"]
    params = [tuple(EXCLUDE_CT_CL)]

    if not args.overwrite:
        where_clauses.append("youtube_video_id IS NULL")

    if args.ct_cl:
        where_clauses.append("ct_cl IN %s")
        params.append(tuple(args.ct_cl))

    sql = (
        "SELECT full_asset_id, asset_nm, ct_cl, provider, series_nm "
        f"FROM vod WHERE {' AND '.join(where_clauses)} "
        "ORDER BY ct_cl, full_asset_id"
    )
    cur.execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    vod_list = [
        {"vod_id": r[0], "asset_nm": r[1], "ct_cl": r[2], "provider": r[3], "series_nm": r[4]}
        for r in rows
    ]

    # 이미 처리된 것 스킵 (--retry-failed 시 failed 항목은 재시도)
    if args.retry_failed:
        already = {k for k, v in status["processed"].items() if v == "success"}
        log.info(f"retry-failed 모드: failed {len(status['processed']) - len(already):,}건 재시도")
    else:
        already = set(status["processed"].keys())
    vod_list = [v for v in vod_list if v["vod_id"] not in already]

    # --partial-series-only: 시리즈 내 성공 에피소드가 1건 이상인 시리즈만 처리
    if args.partial_series_only:
        conn2 = get_db_conn()
        cur2 = conn2.cursor()
        cur2.execute("""
            SELECT DISTINCT series_nm
            FROM vod
            WHERE youtube_video_id IS NOT NULL
              AND series_nm IS NOT NULL AND series_nm != ''
        """)
        partial_series = {r[0] for r in cur2.fetchall()}
        cur2.close()
        conn2.close()
        before = len(vod_list)
        vod_list = [v for v in vod_list if v.get("series_nm") in partial_series]
        log.info(f"partial-series-only: {before:,} → {len(vod_list):,}건 (성공 이력 있는 시리즈만)")

    if args.limit > 0:
        vod_list = vod_list[:args.limit]

    log.info(f"Target: {len(vod_list):,} VODs, Workers: {args.workers}")

    if not vod_list:
        log.info("Nothing to process")
        return

    # ── 병렬 검색 + DB 적재 ───────────────────────────────────────
    results_buffer = []

    def flush_to_db(buf):
        if not buf:
            return
        conn2 = get_db_conn()
        cur2 = conn2.cursor()
        for vod_id, yt_id, dur in buf:
            cur2.execute(
                "UPDATE vod SET youtube_video_id = %s, duration_sec = %s "
                "WHERE full_asset_id = %s",
                (yt_id, dur, vod_id),
            )
        conn2.commit()
        cur2.close()
        conn2.close()

    done = 0
    total = len(vod_list)

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(
                search_youtube,
                v["vod_id"], v["asset_nm"], v["ct_cl"], v["provider"],
                cookies_file,
            ): v
            for v in vod_list
        }

        for future in as_completed(futures):
            vod = futures[future]
            vod_id = vod["vod_id"]
            done += 1

            try:
                result = future.result()
            except Exception as e:
                result = {"status": "failed", "reason": str(e)}

            status["processed"][vod_id] = result.get("status", "failed")

            if result.get("status") == "success":
                yt_id = result["youtube_video_id"]
                dur = result.get("duration_sec")
                if yt_id and len(yt_id) <= 20:
                    results_buffer.append((vod_id, yt_id, dur))
                    status["stats"]["success"] = status["stats"].get("success", 0) + 1
                    if done % 500 == 0 or done <= 5:
                        log.info(
                            f"[{done:,}/{total:,}] OK {vod['asset_nm'][:30]} "
                            f"-> {yt_id}"
                        )
                else:
                    status["stats"]["failed"] = status["stats"].get("failed", 0) + 1
            else:
                status["stats"]["failed"] = status["stats"].get("failed", 0) + 1
                if done % 500 == 0 or done <= 5:
                    log.info(
                        f"[{done:,}/{total:,}] FAIL {vod['asset_nm'][:30]} "
                        f"({result.get('reason', '?')})"
                    )

            # 주기적 flush
            if len(results_buffer) >= BATCH_COMMIT:
                flush_to_db(results_buffer)
                save_status(status)
                log.info(f"  checkpoint: {done:,}/{total:,} "
                         f"(DB flush {len(results_buffer)})")
                results_buffer.clear()

    # 잔여분 flush
    flush_to_db(results_buffer)
    save_status(status)
    results_buffer.clear()

    print_status(status)
    log.info("Done")


if __name__ == "__main__":
    main()
