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
# 기본 trailers 경로 — --trailers-dir 인자로 덮어쓸 수 있음
DEFAULT_TRAILERS_DIR = Path("C:/Users/daewo/DX_prod_2nd/trailers")
STATUS_FILE  = DATA_DIR / "crawl_status.json"

BATCH_SAVE_INTERVAL = 20       # 체크포인트 저장 주기 (파일럿: 20, 전체: 100)
REQUEST_DELAY_MIN   = 1.5      # 요청 간 최소 대기 (초)
REQUEST_DELAY_MAX   = 3.0      # 요청 간 최대 대기 (초)
DURATION_MIN_SEC    = 30
DURATION_MAX_SEC    = 300
MAX_FILESIZE_BYTES  = 50 * 1024 * 1024   # 50MB

# 실제 vod 테이블 ct_cl 값 기준 제외 목록
EXCLUDE_CT_CL = {'키즈', '우리동네', '미분류'}

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


import re as _re

def normalize_title(name: str) -> str:
    """
    DB 저장 제목의 붙여쓰기를 검색 친화적으로 정규화.
    예) '1724기방난동사건' → '1724 기방난동사건'
        '2001스페이스오디세이' → '2001 스페이스오디세이'
    """
    # 숫자↔한글 경계에 공백 삽입
    name = _re.sub(r'(\d)([가-힣])', r'\1 \2', name)
    name = _re.sub(r'([가-힣])(\d)', r'\1 \2', name)
    return name.strip()


def strip_episode_suffix(asset_nm: str) -> str:
    """
    개별 에피소드 정보를 제거해 시리즈 제목만 추출.
    예) '황제의 딸 1 01회'  → '황제의 딸 1'
        '런닝맨 500회'      → '런닝맨'
        '미스터 션샤인 3화'  → '미스터 션샤인'
        '스파이더맨'         → '스파이더맨' (변경 없음)
    """
    # ' N회', 'N화', 'EP.N' 패턴 제거 — 공백 없이 붙은 경우도 처리 (대소문자 무관)
    name = _re.sub(r'\s*\d+\s*[회화]\.?$', '', asset_nm, flags=_re.IGNORECASE)
    name = _re.sub(r'\s+ep\.?\s*\d+$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'\s+\d+\s*e\d*$', '', name, flags=_re.IGNORECASE)
    return name.strip()


def build_search_queries(asset_nm: str, ct_cl: str, genre: str) -> list:
    queries = []
    name     = asset_nm.strip()
    norm     = normalize_title(name)       # 숫자-한글 공백 정규화
    series   = strip_episode_suffix(name)  # 에피소드 번호 제거한 시리즈명

    if ct_cl == '영화':
        queries.append(f"{norm} 예고편")
        if norm != name:                   # 정규화로 달라진 경우만 원본도 추가
            queries.append(f"{name} 예고편")
        queries.append(f"{norm} official trailer")
        queries.append(f"{norm} 공식 예고편")
        queries.append(f"{norm} trailer")
    elif ct_cl in ('TV드라마', 'TV 연예/오락', 'TV 시사/교양'):
        # 시리즈 단위로 검색 (개별 회차 검색하면 결과 없음)
        queries.append(f"{series} 예고편")
        queries.append(f"{series} 하이라이트")
        queries.append(f"{series} 1회")
        queries.append(f"{series} trailer")
    elif ct_cl == 'TV애니메이션':
        queries.append(f"{series} 예고편")
        queries.append(f"{series} trailer")
        queries.append(f"{series} PV")
    else:
        queries.append(f"{name} 예고편")
        queries.append(f"{name} trailer")

    return queries


def duration_filter(info, incomplete):
    """yt-dlp match_filter: 30초~5분 영상만 허용.
    incomplete=True(검색 결과 초기 단계)에서는 duration 미확인이므로 통과시킴."""
    if incomplete:
        return None
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
    """vod 테이블에서 처리 대상 목록 조회 (ct_cl 오름차순 → full_asset_id 오름차순)"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        if ct_cl_filter:
            placeholders = ','.join(['%s'] * len(ct_cl_filter))
            cur.execute(
                f"SELECT full_asset_id, asset_nm, ct_cl, genre "
                f"FROM vod WHERE ct_cl IN ({placeholders}) "
                f"ORDER BY ct_cl, full_asset_id",
                ct_cl_filter
            )
        else:
            excluded = tuple(EXCLUDE_CT_CL)
            cur.execute(
                "SELECT full_asset_id, asset_nm, ct_cl, genre "
                "FROM vod WHERE ct_cl NOT IN %s "
                "ORDER BY ct_cl, full_asset_id",
                (excluded,)
            )
        rows = cur.fetchall()
        return [
            {"vod_id": r[0], "asset_nm": r[1], "ct_cl": r[2], "genre": r[3]}
            for r in rows
        ]
    finally:
        conn.close()


# 파일럿용 ct_cl별 샘플 비율 (합계 100개) — 실제 vod 테이블 ct_cl 기준
PILOT_SAMPLE_PLAN = {
    "TV드라마":      40,
    "영화":          25,
    "TV 연예/오락":  15,
    "TV애니메이션":   8,
    "TV 시사/교양":   5,
    "다큐":           4,
    "_others":        3,   # 위에 없는 ct_cl (교육, 스포츠, 공연/음악 등)
}

# 시리즈 단위 dedup이 필요한 ct_cl (에피소드가 여러 개인 콘텐츠)
SERIES_CT_CL = {'TV드라마', 'TV 연예/오락', 'TV 시사/교양', 'TV애니메이션'}

def dedup_by_series(pool: list) -> list:
    """
    같은 시리즈명(strip_episode_suffix 기준)에서 full_asset_id가 가장 낮은
    에피소드 1개만 남긴다. pool은 full_asset_id 오름차순 정렬된 상태여야 함.
    예) '황제의 딸 1 01회' ~ '황제의 딸 1 40회' → '황제의 딸 1 01회' 1개만 유지
    """
    seen_series = set()
    result = []
    for v in pool:
        series_key = strip_episode_suffix(v["asset_nm"])
        if series_key not in seen_series:
            seen_series.add(series_key)
            result.append(v)
    return result


def stratified_sample(vod_list: list, total: int = 100) -> list:
    """
    ct_cl 계층별 층화 샘플 추출.
    PILOT_SAMPLE_PLAN 비율로 각 카테고리에서 추출.
    TV 계열은 시리즈 단위 dedup 후 quota개 선택 (같은 시리즈 중복 방지).
    """
    from collections import defaultdict
    buckets = defaultdict(list)
    for v in vod_list:
        ct = v["ct_cl"]
        if ct in PILOT_SAMPLE_PLAN:
            buckets[ct].append(v)
        else:
            buckets["_others"].append(v)

    result = []
    for ct, quota in PILOT_SAMPLE_PLAN.items():
        pool = buckets.get(ct, [])
        if ct in SERIES_CT_CL:
            pool = dedup_by_series(pool)   # 시리즈 단위 중복 제거
        result.extend(pool[:quota])

    # quota 합산이 total에 못 미치면 나머지로 채움
    if len(result) < total:
        sampled_ids = {v["vod_id"] for v in result}
        for v in vod_list:
            if len(result) >= total:
                break
            if v["vod_id"] not in sampled_ids:
                result.append(v)

    log.info(f"층화 샘플 구성:")
    ct_counts = {}
    for v in result:
        ct_counts[v["ct_cl"]] = ct_counts.get(v["ct_cl"], 0) + 1
    for ct, cnt in sorted(ct_counts.items()):
        log.info(f"  {ct}: {cnt}개")

    return result[:total]


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
    parser.add_argument('--pilot', action='store_true',
                        help='ct_cl 층화 100개 파일럿 실행 (시간/성공률 검증용)')
    parser.add_argument('--trailers-dir', type=str, default=str(DEFAULT_TRAILERS_DIR),
                        help=f'트레일러 저장 경로 (기본: {DEFAULT_TRAILERS_DIR})')
    args = parser.parse_args()
    TRAILERS_DIR = Path(args.trailers_dir)

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

    # --pilot: ct_cl 층화 100개 샘플
    if args.pilot:
        log.info("=== 파일럿 모드: ct_cl 층화 100개 샘플 ===")
        vod_list = stratified_sample(vod_list, total=100)
        status["mode"] = "pilot"
    elif args.limit > 0:
        vod_list = vod_list[:args.limit]
        log.info(f"--limit {args.limit} 적용")

    status["total"] = len(vod_list)
    log.info(f"대상 VOD: {len(vod_list):,}개")

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
