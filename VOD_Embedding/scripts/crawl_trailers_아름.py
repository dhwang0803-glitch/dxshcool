"""
TV 연예/오락 에피소드별 트레일러 재수집 스크립트 (박아름)

기존 crawl_trailers.py의 문제:
  - TV 연예/오락도 시리즈명 기준 쿼리 사용 → 9,570건이 829개 파일 공유
  - 에피소드별 게스트·장소 등 개별 영상 특성 미반영

개선:
  1. 에피소드별 쿼리: "{시리즈명} {N}회"
  2. 날짜 fallback:  "{시리즈명} {YYYY}년 {MM}월 {DD}일"
  3. 최종 fallback:  "{시리즈명} 예고편" (기존 방식)

출력:
  - 트레일러: data/trailers_아름/ (기존 data/trailers/ 와 분리)
  - 상태 파일: data/crawl_status_아름.json

실행:
    cd VOD_Embedding
    python scripts/crawl_trailers_아름.py
    python scripts/crawl_trailers_아름.py --status
    python scripts/crawl_trailers_아름.py --dry-run --limit 10
"""

import sys
import os
import json
import time
import random
import argparse
import logging
import re
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT  = Path(__file__).parent.parent
DATA_DIR      = PROJECT_ROOT / "data"
TRAILERS_DIR  = DATA_DIR / "trailers_아름"
STATUS_FILE   = DATA_DIR / "crawl_status_아름.json"

BATCH_SAVE_INTERVAL = 20
REQUEST_DELAY_MIN   = 1.5
REQUEST_DELAY_MAX   = 3.0
DURATION_MIN_SEC    = 30
DURATION_MAX_SEC    = 300
MAX_FILESIZE_BYTES  = 50 * 1024 * 1024   # 50MB

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "crawl_아름.log", encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DB 연결
# ---------------------------------------------------------------------------

def load_env():
    for candidate in [
        PROJECT_ROOT.parent / "Database_Design" / ".env",
        PROJECT_ROOT.parent / ".env",
        PROJECT_ROOT / ".env",
    ]:
        if candidate.exists():
            env = {}
            with open(candidate, encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        k, v = line.split('=', 1)
                        env[k.strip()] = v.strip()
            return env
    return {}


def get_db_conn():
    env = load_env()
    import psycopg2
    return psycopg2.connect(
        host=os.getenv('DB_HOST') or env.get('DB_HOST'),
        port=os.getenv('DB_PORT') or env.get('DB_PORT', 5432),
        dbname=os.getenv('DB_NAME') or env.get('DB_NAME'),
        user=os.getenv('DB_USER') or env.get('DB_USER'),
        password=os.getenv('DB_PASSWORD') or env.get('DB_PASSWORD'),
    )


# ---------------------------------------------------------------------------
# 상태 파일
# ---------------------------------------------------------------------------

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


def print_status(status: dict):
    total     = status.get("total", 0)
    processed = status.get("processed", 0)
    success   = status.get("success", 0)
    failed    = status.get("failed", 0)
    pct = f"{processed/total*100:.1f}%" if total > 0 else "0%"
    print(f"\n=== 크롤링 진행 현황 (박아름 — 에피소드별 재수집) ===")
    print(f"  전체 대상: {total:,}개")
    print(f"  처리 완료: {processed:,}개 ({pct})")
    print(f"  성공:      {success:,}개")
    print(f"  실패:      {failed:,}개")
    print(f"  마지막 갱신: {status.get('last_updated', 'N/A')}")
    print()


# ---------------------------------------------------------------------------
# VOD 조회 (release_date 포함)
# ---------------------------------------------------------------------------

def fetch_entertainment_vods() -> list:
    """
    TV 연예/오락 전체 에피소드 조회.
    release_date 포함 — 날짜 기반 검색 쿼리 생성에 사용.
    tasks_A.json 앞 절반만 처리 (박아름 담당 분).
    """
    log.info("DB에서 TV 연예/오락 에피소드 조회 중...")
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT full_asset_id, asset_nm, ct_cl, genre, series_nm, release_date
            FROM vod
            WHERE ct_cl = 'TV 연예/오락'
            ORDER BY full_asset_id
            """
        )
        rows = cur.fetchall()
    finally:
        conn.close()

    all_vods = [
        {
            "vod_id":       r[0],
            "asset_nm":     r[1],
            "ct_cl":        r[2],
            "genre":        r[3],
            "series_nm":    r[4],
            "release_date": str(r[5]) if r[5] else None,
        }
        for r in rows
    ]

    # 박아름 담당: full_asset_id 정렬 기준 앞 절반
    mid = len(all_vods) // 2
    team_a = all_vods[:mid]
    log.info(f"  전체 TV 연예/오락: {len(all_vods):,}건 → 박아름 담당(앞 절반): {len(team_a):,}건")
    return team_a


# ---------------------------------------------------------------------------
# 에피소드별 검색 쿼리 생성
# ---------------------------------------------------------------------------

def extract_episode_number(asset_nm: str):
    """asset_nm에서 회차 번호 추출. 예) '런닝맨 350회' → '350'"""
    m = re.search(r'(\d+)\s*[회화]', asset_nm)
    return m.group(1) if m else None


def extract_series_name(asset_nm: str) -> str:
    """에피소드 번호 제거한 시리즈명 추출."""
    name = re.sub(r'\s*\d+\s*[회화]\.?$', '', asset_nm)
    name = re.sub(r'\s+ep\.?\s*\d+$', '', name, flags=re.IGNORECASE)
    return name.strip()


def build_episode_queries(asset_nm: str, series_nm: str, release_date: str) -> list:
    """
    에피소드별 검색 쿼리 우선순위:
      1. "{시리즈명} {N}회"           — 회차 번호 검색
      2. "{시리즈명} {YYYY}년 {M}월 {D}일" — 방송 날짜 검색
      3. "{시리즈명} 예고편"            — 시리즈 fallback
      4. "{시리즈명} 하이라이트"
      5. "{시리즈명} 1회"
    """
    # 시리즈명 결정: DB series_nm 우선, 없으면 asset_nm에서 추출
    series = (series_nm.strip() if series_nm and series_nm.strip()
              else extract_series_name(asset_nm))

    queries = []

    # 1. 회차 번호 검색
    ep_num = extract_episode_number(asset_nm)
    if ep_num:
        queries.append(f"{series} {ep_num}회")

    # 2. 방송 날짜 검색
    if release_date:
        try:
            from datetime import date as _date
            d = _date.fromisoformat(release_date[:10])
            queries.append(f"{series} {d.year}년 {d.month}월 {d.day}일")
        except Exception:
            pass

    # 3. 시리즈 fallback
    queries.append(f"{series} 예고편")
    queries.append(f"{series} 하이라이트")
    queries.append(f"{series} 1회")

    return queries


# ---------------------------------------------------------------------------
# 다운로드
# ---------------------------------------------------------------------------

def duration_filter(info, incomplete):
    if incomplete:
        return None
    duration = info.get('duration') or 0
    if duration < DURATION_MIN_SEC:
        return f"너무 짧음 ({duration}초)"
    if duration > DURATION_MAX_SEC:
        return f"너무 김 ({duration}초)"
    return None


def try_download(vod_id: str, queries: list, output_dir: Path, dry_run: bool) -> dict:
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
            'default_search': 'ytsearch1',
            'noplaylist': True,
        }

        if dry_run:
            log.info(f"[DRY-RUN] {vod_id}: 쿼리 = '{query}'")
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


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="TV 연예/오락 에피소드별 트레일러 재수집 (박아름)")
    parser.add_argument('--dry-run', action='store_true', help='실제 다운로드 없이 쿼리 확인')
    parser.add_argument('--limit', type=int, default=0, help='처리 건수 제한 (테스트용)')
    parser.add_argument('--status', action='store_true', help='진행 상황만 출력')
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = load_status()

    if args.status:
        print_status(status)
        return

    vod_list = fetch_entertainment_vods()

    if args.limit > 0:
        vod_list = vod_list[:args.limit]
        log.info(f"--limit {args.limit} 적용")

    status["total"] = len(vod_list)
    log.info(f"대상: {len(vod_list):,}건 (TV 연예/오락 에피소드별 개별 수집)")

    for i, vod in enumerate(vod_list):
        vod_id = vod["vod_id"]

        if vod_id in status["vods"] and status["vods"][vod_id]["status"] in ("success", "skipped"):
            continue

        queries = build_episode_queries(
            vod["asset_nm"],
            vod.get("series_nm"),
            vod.get("release_date"),
        )
        result = try_download(vod_id, queries, TRAILERS_DIR, args.dry_run)

        result["asset_nm"]     = vod["asset_nm"]
        result["series_nm"]    = vod.get("series_nm")
        result["release_date"] = vod.get("release_date")
        status["vods"][vod_id] = result
        status["processed"] = status.get("processed", 0) + 1

        if result["status"] == "success":
            status["success"] = status.get("success", 0) + 1
            log.info(
                f"[{i+1}/{len(vod_list)}] OK   {vod['asset_nm']} "
                f"→ {result['filename']} (쿼리: {result['query_used']})"
            )
        else:
            status["failed"] = status.get("failed", 0) + 1
            log.warning(
                f"[{i+1}/{len(vod_list)}] FAIL {vod['asset_nm']} "
                f"(시도: {queries})"
            )

        if (i + 1) % BATCH_SAVE_INTERVAL == 0:
            save_status(status)

    save_status(status)
    log.info(
        f"=== 완료 === 성공: {status['success']:,} / 실패: {status['failed']:,} "
        f"/ 전체: {status['total']:,}"
    )


if __name__ == "__main__":
    main()
