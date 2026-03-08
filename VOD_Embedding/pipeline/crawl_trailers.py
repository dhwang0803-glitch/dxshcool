"""
PLAN_01: YouTube 트레일러 수집
vod 테이블 → YouTube 검색 → yt-dlp 다운로드 → trailers/*.webm

실행:
    conda activate myenv
    python pipeline/crawl_trailers.py
    python pipeline/crawl_trailers.py --dry-run --limit 10
    python pipeline/crawl_trailers.py --status
"""

import sys
import os
import json
import time
import random
import argparse
import logging
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트 기준 경로
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
TRAILERS_DIR = PROJECT_ROOT.parent / "trailers"   # 기존 로컬 trailers 폴더와 동일
STATUS_FILE  = DATA_DIR / "crawl_status.json"

BATCH_SAVE_INTERVAL = 100      # 체크포인트 저장 주기
REQUEST_DELAY_MIN   = 1.5      # 요청 간 최소 대기 (초)
REQUEST_DELAY_MAX   = 3.0      # 요청 간 최대 대기 (초)
DURATION_MIN_SEC    = 30
DURATION_MAX_SEC    = 300
MAX_FILESIZE_BYTES  = 50 * 1024 * 1024   # 50MB

EXCLUDE_CT_CL = {'홈쇼핑'}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "crawl.log", encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)


def load_env():
    """Database_Design/.env 로드"""
    env_path = PROJECT_ROOT.parent / "Database_Design" / ".env"
    if not env_path.exists():
        # 같은 레벨 .env 시도
        env_path = PROJECT_ROOT.parent / ".env"
    env = {}
    if env_path.exists():
        with open(env_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env[k.strip()] = v.strip()
    return env


def get_db_conn():
    env = load_env()
    import psycopg2
    return psycopg2.connect(
        host=env.get('DB_HOST', 'localhost'),
        port=env.get('DB_PORT', 5432),
        dbname=env.get('DB_NAME', 'postgres'),
        user=env.get('DB_USER', 'postgres'),
        password=env.get('DB_PASSWORD', ''),
    )


def load_status() -> dict:
    if STATUS_FILE.exists():
        with open(STATUS_FILE, encoding='utf-8') as f:
            return json.load(f)
    return {
        "last_updated": None,
        "total": 0,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "vods": {}
    }


def save_status(status: dict):
    status["last_updated"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def build_search_queries(asset_nm: str, ct_cl: str, genre: str) -> list:
    queries = []
    name = asset_nm.strip()

    queries.append(f"{name} 예고편")
    queries.append(f"{name} trailer")

    if ct_cl == '영화':
        queries.append(f"{name} official trailer")
        queries.append(f"{name} 공식 예고편")
    elif ct_cl in ('드라마', '예능'):
        queries.append(f"{name} 하이라이트")

    return queries


def duration_filter(info, incomplete):
    """yt-dlp match_filter: 30초~5분 영상만 허용"""
    duration = info.get('duration') or 0
    if duration < DURATION_MIN_SEC:
        return f"너무 짧음 ({duration}초)"
    if duration > DURATION_MAX_SEC:
        return f"너무 김 ({duration}초)"
    return None


def try_download(vod_id: str, queries: list, output_dir: Path, dry_run: bool) -> dict:
    """
    쿼리 목록을 순서대로 시도하여 첫 번째 성공 시 반환.
    반환: {"status": "success"|"failed", ...}
    """
    try:
        import yt_dlp
    except ImportError:
        log.error("yt-dlp 미설치: pip install yt-dlp")
        return {"status": "error", "reason": "yt_dlp_not_installed"}

    output_dir.mkdir(parents=True, exist_ok=True)

    for query in queries:
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

        ydl_opts = {
            'format': 'worst[ext=webm]/worst',
            'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'match_filter': duration_filter,
            'max_filesize': MAX_FILESIZE_BYTES,
            'retries': 2,
            'socket_timeout': 30,
            'default_search': 'ytsearch1',   # 첫 번째 검색 결과만
            'noplaylist': True,
        }

        if dry_run:
            log.info(f"[DRY-RUN] {vod_id}: 검색 쿼리 = '{query}'")
            return {
                "status": "success",
                "filename": "dry_run.webm",
                "query_used": query,
                "duration_sec": 0,
                "downloaded_at": datetime.now().isoformat(),
            }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{query}", download=True)
                if info and info.get('entries'):
                    entry = info['entries'][0]
                    filename = f"{entry['id']}.{entry.get('ext', 'webm')}"
                    return {
                        "status": "success",
                        "filename": filename,
                        "query_used": query,
                        "duration_sec": entry.get('duration', 0),
                        "downloaded_at": datetime.now().isoformat(),
                    }
        except Exception as e:
            err_str = str(e)
            if '429' in err_str or 'Too Many Requests' in err_str:
                log.warning("YouTube 429 — 60초 대기")
                time.sleep(60)
            log.debug(f"{vod_id} 쿼리 실패 '{query}': {e}")
            continue

    return {
        "status": "failed",
        "reason": "no_result",
        "tried_queries": queries,
        "failed_at": datetime.now().isoformat(),
    }


def fetch_vod_list(ct_cl_filter=None) -> list:
    """vod 테이블에서 처리 대상 목록 조회"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        if ct_cl_filter:
            placeholders = ','.join(['%s'] * len(ct_cl_filter))
            cur.execute(
                f"SELECT full_asset_id, asset_nm, ct_cl, genre "
                f"FROM vod WHERE ct_cl IN ({placeholders}) ORDER BY full_asset_id",
                ct_cl_filter
            )
        else:
            excluded = tuple(EXCLUDE_CT_CL)
            cur.execute(
                "SELECT full_asset_id, asset_nm, ct_cl, genre "
                "FROM vod WHERE ct_cl NOT IN %s ORDER BY full_asset_id",
                (excluded,)
            )
        rows = cur.fetchall()
        return [
            {"vod_id": r[0], "asset_nm": r[1], "ct_cl": r[2], "genre": r[3]}
            for r in rows
        ]
    finally:
        conn.close()


def print_status(status: dict):
    total     = status.get("total", 0)
    processed = status.get("processed", 0)
    success   = status.get("success", 0)
    failed    = status.get("failed", 0)
    pct = f"{processed/total*100:.1f}%" if total > 0 else "0%"

    print(f"\n=== 크롤링 진행 현황 ===")
    print(f"  전체 대상: {total:,}개")
    print(f"  처리 완료: {processed:,}개 ({pct})")
    print(f"  성공:      {success:,}개")
    print(f"  실패:      {failed:,}개")
    print(f"  마지막 갱신: {status.get('last_updated', 'N/A')}")
    print()


def main():
    parser = argparse.ArgumentParser(description="VOD 트레일러 수집")
    parser.add_argument('--dry-run', action='store_true', help='실제 다운로드 없이 로직 확인')
    parser.add_argument('--limit', type=int, default=0, help='처리 건수 제한 (테스트용)')
    parser.add_argument('--ct-cl', nargs='+', help='특정 ct_cl만 처리 (예: 영화 드라마)')
    parser.add_argument('--status', action='store_true', help='진행 상황만 출력')
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = load_status()

    if args.status:
        print_status(status)
        return

    # VOD 목록 로드
    log.info("vod 테이블에서 대상 목록 조회 중...")
    try:
        vod_list = fetch_vod_list(ct_cl_filter=args.ct_cl)
    except Exception as e:
        log.error(f"DB 연결 실패: {e}")
        log.info("테스트용 샘플 데이터로 대체합니다.")
        vod_list = [
            {"vod_id": "TEST001", "asset_nm": "어바웃 타임", "ct_cl": "영화", "genre": "로맨스"},
            {"vod_id": "TEST002", "asset_nm": "기생충", "ct_cl": "영화", "genre": "드라마"},
        ]

    status["total"] = len(vod_list)
    log.info(f"대상 VOD: {len(vod_list):,}개")

    if args.limit > 0:
        vod_list = vod_list[:args.limit]
        log.info(f"--limit {args.limit} 적용")

    done_count = 0
    for i, vod in enumerate(vod_list):
        vod_id = vod["vod_id"]

        # 이미 처리된 항목 스킵
        if vod_id in status["vods"] and status["vods"][vod_id]["status"] in ("success", "skipped"):
            continue

        queries = build_search_queries(vod["asset_nm"], vod["ct_cl"], vod["genre"])
        result  = try_download(vod_id, queries, TRAILERS_DIR, args.dry_run)

        status["vods"][vod_id] = result
        status["processed"] = status.get("processed", 0) + 1

        if result["status"] == "success":
            status["success"] = status.get("success", 0) + 1
            log.info(f"[{i+1}/{len(vod_list)}] OK  {vod_id} ({vod['asset_nm']}) → {result['filename']}")
        else:
            status["failed"] = status.get("failed", 0) + 1
            log.warning(f"[{i+1}/{len(vod_list)}] FAIL {vod_id} ({vod['asset_nm']}): {result.get('reason')}")

        done_count += 1
        if done_count % BATCH_SAVE_INTERVAL == 0:
            save_status(status)
            log.info(f"체크포인트 저장 ({done_count}건 처리)")

    save_status(status)
    print_status(status)
    log.info("크롤링 완료")


if __name__ == "__main__":
    main()
