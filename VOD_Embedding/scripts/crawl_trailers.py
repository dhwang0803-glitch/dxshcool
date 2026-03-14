"""
PLAN_01: YouTube 트레일러 수집
vod 테이블 → YouTube 검색 → yt-dlp 다운로드 → trailers/*.webm

실행:
    conda activate myenv
    python scripts/crawl_trailers.py                                # 전체 실행
    python scripts/crawl_trailers.py --dry-run --limit 10
    python scripts/crawl_trailers.py --status
    python scripts/crawl_trailers.py --task-file data/tasks_missing.json   # 미완료 시리즈 처리
    python scripts/crawl_trailers.py --task-file data/tasks_A.json         # 팀원 분할 파일

검색 전략:
    - 방송사(provider) 기반 검색 키워드 추가로 정확도 향상
      (KBS/MBC/SBS/JTBC/CJ ENM/EBS → 방송사명 쿼리에 포함)
    - 상위 3개 결과(ytsearch3) 후보 중 최적 트레일러 선별
      선별 기준: ① 60~600초 이내 ② 트레일러 키워드 포함 ③ 최단 길이 우선
    - 시리즈 단위 ct_cl: 대표 에피소드 1개 크롤링 → --propagate로 전파
    - 에피소드 단위 ct_cl (TV 연예/오락): 에피소드별 개별 크롤링
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

import re as _re

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR     = PROJECT_ROOT / "data"
DEFAULT_TRAILERS_DIR = Path("C:/Users/daewo/DX_prod_2nd/trailers")
STATUS_FILE  = DATA_DIR / "crawl_status.json"   # --status-file 인자로 덮어씀

BATCH_SAVE_INTERVAL   = 20        # 체크포인트 저장 주기 (파일럿: 20, 전체: 100)
REQUEST_DELAY_MIN     = 1.5       # 요청 간 최소 대기 (초)
REQUEST_DELAY_MAX     = 3.0       # 요청 간 최대 대기 (초)
DURATION_MIN_SEC      = 30
DURATION_MAX_SEC      = 300               # fast path 기준 (기존 유지)
DURATION_MAX_SEC_SLOW = 600               # slow path fallback 기준 (5→10분)
MAX_RESULTS           = 3                 # 기존 1 → 3 (최적 트레일러 선별)
MAX_FILESIZE_BYTES    = 100 * 1024 * 1024  # 100MB (600초 기준 상향)

EXCLUDE_CT_CL       = {'우리동네', '미분류'}
SERIES_EMBED_CT_CL  = {'TV드라마', 'TV 시사/교양', 'TV애니메이션', '키즈', '영화'}
EPISODE_EMBED_CT_CL = {'TV 연예/오락'}

# provider → YouTube 검색 키워드 매핑
# 목록에 없는 provider(애니메이션/해외드라마/영화 등)는 키워드 없이 제목만 사용
PROVIDER_KEYWORD = {
    'KBS':    'KBS',
    'MBC':    'MBC',
    'SBS':    'SBS',
    'JTBC':   'JTBC',
    'CJ ENM': 'tvN',
    'EBS':    'EBS',
}

# 트레일러 관련 키워드 — 선별 점수 산정에 사용
_TRAILER_KEYWORDS = ('예고편', '공식', 'official', 'trailer', 'teaser', 'preview',
                     '하이라이트', 'highlight', 'PV', '프로모', 'promo')

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
    env_path = PROJECT_ROOT.parent / "Database_Design" / ".env"
    if not env_path.exists():
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
        host=env.get('DB_HOST'),
        port=env.get('DB_PORT', 5432),
        dbname=env.get('DB_NAME'),
        user=env.get('DB_USER'),
        password=env.get('DB_PASSWORD'),
    )


def load_status(status_file: Path) -> dict:
    if status_file.exists():
        with open(status_file, encoding='utf-8') as f:
            return json.load(f)
    return {
        "last_updated": None,
        "total": 0,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "vods": {}
    }


def save_status(status: dict, status_file: Path):
    status["last_updated"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(status_file, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def normalize_title(name: str) -> str:
    """숫자↔한글 경계에 공백 삽입 (검색 정확도 향상)"""
    name = _re.sub(r'(\d)([가-힣])', r'\1 \2', name)
    name = _re.sub(r'([가-힣])(\d)', r'\1 \2', name)
    return name.strip()


def strip_episode_suffix(asset_nm: str) -> str:
    """에피소드 번호 제거 후 순수 시리즈명 반환"""
    name = _re.sub(r'\s*\d+\s*[회화]\.?$', '', asset_nm, flags=_re.IGNORECASE)
    name = _re.sub(r'\s+ep\.?\s*\d+$', '', name, flags=_re.IGNORECASE)
    name = _re.sub(r'\s+\d+\s*e\d*$', '', name, flags=_re.IGNORECASE)
    return name.strip()


def build_search_queries(asset_nm: str, ct_cl: str, genre: str,
                         series_nm: str = None, provider: str = None) -> list:
    """
    검색 쿼리 목록 생성.
    provider가 PROVIDER_KEYWORD에 있으면 '제목 + 방송사' 쿼리를 우선 배치.
    """
    queries = []
    name      = asset_nm.strip()
    norm      = normalize_title(name)
    series    = strip_episode_suffix(name)
    movie_nm  = normalize_title(series_nm.strip()) if series_nm else norm

    # 방송사 키워드 — 없으면 빈 문자열
    bc = PROVIDER_KEYWORD.get(provider, '') if provider else ''

    if ct_cl == '영화':
        if bc:
            queries.append(f"{movie_nm} {bc} 예고편")
        queries.append(f"{movie_nm} 예고편")
        queries.append(f"{movie_nm} official trailer")
        queries.append(f"{movie_nm} 공식 예고편")
        queries.append(f"{movie_nm} trailer")

    elif ct_cl in ('TV드라마', 'TV 시사/교양'):
        if bc:
            queries.append(f"{series} {bc} 예고편")
            queries.append(f"{series} {bc} 1회")
        queries.append(f"{series} 예고편")
        queries.append(f"{series} 하이라이트")
        queries.append(f"{series} 1회")
        queries.append(f"{series} trailer")

    elif ct_cl == 'TV 연예/오락':
        if bc:
            queries.append(f"{series} {bc} 예고편")
        queries.append(f"{series} 예고편")
        queries.append(f"{series} 하이라이트")
        queries.append(f"{series} 1회")
        queries.append(f"{series} trailer")

    elif ct_cl == 'TV애니메이션':
        queries.append(f"{series} 예고편")
        queries.append(f"{series} trailer")
        queries.append(f"{series} PV")
        queries.append(f"{series} 공식 예고편")

    else:
        if bc:
            queries.append(f"{norm} {bc} 예고편")
        queries.append(f"{norm} 예고편")
        queries.append(f"{norm} trailer")

    # 중복 제거 (순서 유지)
    seen = set()
    deduped = []
    for q in queries:
        if q not in seen:
            seen.add(q)
            deduped.append(q)
    return deduped


def score_entry(entry: dict) -> int:
    """
    후보 영상 선별 점수 산정 (높을수록 트레일러에 적합).
    duration, 제목 키워드 기준.
    """
    score    = 0
    duration = entry.get('duration') or 0
    title    = (entry.get('title') or '').lower()

    # 트레일러 키워드 포함 여부
    for kw in _TRAILER_KEYWORDS:
        if kw.lower() in title:
            score += 3
            break

    # 60~300초: 전형적인 예고편 길이 → 최우선
    if 60 <= duration <= 300:
        score += 2
    # 300~600초: 긴 예고편/하이라이트 → 차선
    elif 30 <= duration < 60 or 300 < duration <= 600:
        score += 1

    return score


def pick_best_entry(entries: list) -> dict | None:
    """
    duration 범위 내 후보 중 score 최고 → score 동점 시 duration 짧은 것 우선.
    """
    valid = [
        e for e in entries
        if e and DURATION_MIN_SEC <= (e.get('duration') or 0) <= DURATION_MAX_SEC
    ]
    if not valid:
        return None
    return sorted(valid, key=lambda e: (-score_entry(e), e.get('duration') or 9999))[0]


def duration_filter_slow(info, incomplete):
    """slow path용 match_filter: 30초~10분 허용."""
    if incomplete:
        return None
    duration = info.get('duration') or 0
    if duration < DURATION_MIN_SEC:
        return f"너무 짧음 ({duration}초)"
    if duration > DURATION_MAX_SEC_SLOW:
        return f"너무 김 ({duration}초)"
    return None


def try_download(vod_id: str, queries: list, output_dir: Path, dry_run: bool,
                 slow: bool = False) -> dict:
    """
    쿼리 목록을 순서대로 시도.
    각 쿼리에서 상위 MAX_RESULTS개 후보를 가져와 최적 트레일러 선별 후 다운로드.

    slow=False (기본 fast path): ytsearch1, DURATION_MAX 300s — 기존 동작 유지
    slow=True  (slow path):      ytsearch3, DURATION_MAX 600s — fast 실패 시 fallback

    반환: {"status": "success"|"failed", ...}
    """
    try:
        import yt_dlp
    except ImportError:
        log.error("yt-dlp 미설치: pip install yt-dlp")
        return {"status": "error", "reason": "yt_dlp_not_installed"}

    output_dir.mkdir(parents=True, exist_ok=True)

    n_results   = 3 if slow else 1
    dur_filter  = duration_filter_slow if slow else duration_filter
    dur_max     = DURATION_MAX_SEC_SLOW if slow else DURATION_MAX_SEC

    for query in queries:
        time.sleep(random.uniform(REQUEST_DELAY_MIN, REQUEST_DELAY_MAX))

        if dry_run:
            log.info(f"[DRY-RUN] {vod_id}: 검색 쿼리 = '{query}' (slow={slow})")
            return {
                "status": "success",
                "filename": "dry_run.webm",
                "query_used": query,
                "duration_sec": 0,
                "downloaded_at": datetime.now().isoformat(),
            }

        # ── Step 1: 메타데이터만 수집 (MAX_RESULTS개) ──────────────────────
        meta_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'extract_flat': False,
            'default_search': f'ytsearch{MAX_RESULTS}',
            'noplaylist': True,
            'socket_timeout': 30,
        }
        try:
            with yt_dlp.YoutubeDL(meta_opts) as ydl:
                info = ydl.extract_info(f"ytsearch{MAX_RESULTS}:{query}", download=False)
            entries = info.get('entries', []) if info else []
        except Exception as e:
            err = str(e)
            if '429' in err or 'Too Many Requests' in err:
                log.warning("YouTube 429 — 60초 대기")
                time.sleep(60)
            log.debug(f"{vod_id} 메타 수집 실패 '{query}': {e}")
            continue

        # ── Step 2: 최적 후보 선별 ──────────────────────────────────────────
        best = pick_best_entry(entries)
        if best is None:
            log.debug(f"{vod_id} 유효 후보 없음 '{query}' "
                      f"(후보 {len(entries)}개, duration={[e.get('duration') for e in entries]})")
            continue

        # ── Step 3: 선별된 영상만 다운로드 ─────────────────────────────────
        dl_opts = {
            'format': 'worst[ext=webm]/worst',
            'outtmpl': str(output_dir / '%(id)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'max_filesize': MAX_FILESIZE_BYTES,
            'retries': 2,
            'socket_timeout': 30,
            'noplaylist': True,
        }
        try:
            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                ydl.download([f"https://www.youtube.com/watch?v={best['id']}"])
            filename = f"{best['id']}.{best.get('ext', 'webm')}"
            return {
                "status": "success",
                "filename": filename,
                "query_used": query,
                "youtube_title": best.get('title', ''),
                "duration_sec": best.get('duration', 0),
                "score": score_entry(best),
                "downloaded_at": datetime.now().isoformat(),
            }
        except Exception as e:
            err = str(e)
            if '429' in err or 'Too Many Requests' in err:
                log.warning("YouTube 429 — 60초 대기")
                time.sleep(60)
            log.debug(f"{vod_id} 다운로드 실패 '{best.get('id')}': {e}")
            continue

    return {
        "status": "failed",
        "reason": "no_result",
        "tried_queries": queries,
        "failed_at": datetime.now().isoformat(),
    }


def fetch_vod_list(ct_cl_filter=None) -> list:
    """vod 테이블에서 처리 대상 목록 조회 (provider 포함)"""
    conn = get_db_conn()
    try:
        cur = conn.cursor()
        if ct_cl_filter:
            placeholders = ','.join(['%s'] * len(ct_cl_filter))
            cur.execute(
                f"SELECT full_asset_id, asset_nm, ct_cl, genre, series_nm, provider "
                f"FROM vod WHERE ct_cl IN ({placeholders}) "
                f"ORDER BY ct_cl, full_asset_id",
                ct_cl_filter
            )
        else:
            excluded = tuple(EXCLUDE_CT_CL)
            cur.execute(
                "SELECT full_asset_id, asset_nm, ct_cl, genre, series_nm, provider "
                "FROM vod WHERE ct_cl NOT IN %s "
                "ORDER BY ct_cl, full_asset_id",
                (excluded,)
            )
        rows = cur.fetchall()
        return [
            {"vod_id": r[0], "asset_nm": r[1], "ct_cl": r[2],
             "genre": r[3], "series_nm": r[4], "provider": r[5]}
            for r in rows
        ]
    finally:
        conn.close()


PILOT_SAMPLE_PLAN = {
    "TV드라마":      40,
    "영화":          25,
    "TV 연예/오락":  15,
    "TV애니메이션":   8,
    "TV 시사/교양":   5,
    "다큐":           4,
    "_others":        3,
}

_BAD_SERIES_NM = {
    '애니메이션', '일본 AV', '성인', 'AV', '성인물',
    '키즈', '교육', '기타', '다큐', '스포츠', '공연/음악', '라이프',
    '우리동네', '미분류', '드라마', '영화', 'TV',
}


def effective_series_nm(series_nm, asset_nm: str) -> tuple:
    if series_nm and series_nm.strip() not in _BAD_SERIES_NM:
        return series_nm.strip(), False
    return strip_episode_suffix(asset_nm), True


def dedup_by_series_nm(pool: list) -> list:
    seen = set()
    result = []
    for v in pool:
        key, _ = effective_series_nm(v.get("series_nm"), v["asset_nm"])
        if key not in seen:
            seen.add(key)
            result.append(v)
    return result


def stratified_sample(vod_list: list, total: int = 100) -> list:
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
        if ct in SERIES_EMBED_CT_CL:
            pool = dedup_by_series_nm(pool)
        result.extend(pool[:quota])

    if len(result) < total:
        sampled_ids = {v["vod_id"] for v in result}
        for v in vod_list:
            if len(result) >= total:
                break
            if v["vod_id"] not in sampled_ids:
                result.append(v)

    ct_counts = {}
    for v in result:
        ct_counts[v["ct_cl"]] = ct_counts.get(v["ct_cl"], 0) + 1
    log.info("층화 샘플 구성:")
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
    parser.add_argument('--dry-run',     action='store_true', help='실제 다운로드 없이 로직 확인')
    parser.add_argument('--limit',       type=int, default=0, help='처리 건수 제한 (테스트용)')
    parser.add_argument('--ct-cl',       nargs='+', help='특정 ct_cl만 처리')
    parser.add_argument('--status',      action='store_true', help='진행 상황만 출력')
    parser.add_argument('--pilot',       action='store_true', help='ct_cl 층화 100개 파일럿 실행')
    parser.add_argument('--trailers-dir', type=str, default=str(DEFAULT_TRAILERS_DIR),
                        help=f'트레일러 저장 경로 (기본: {DEFAULT_TRAILERS_DIR})')
    parser.add_argument('--task-file',   type=str, default='',
                        help='작업 파일 경로 (tasks_missing.json / tasks_A.json 등). '
                             '지정 시 --ct-cl/--pilot 무시')
    parser.add_argument('--status-file', type=str, default='',
                        help='크롤 상태 저장 파일 (기본: data/crawl_status.json). '
                             '병렬 실행 시 파티션별로 다르게 지정')
    parser.add_argument('--retry-failed', action='store_true',
                        help='crawl_status.json의 failed 건을 slow path(ytsearch3+600s)로 재시도')
    args = parser.parse_args()
    TRAILERS_DIR = Path(args.trailers_dir)
    STATUS_FILE  = Path(args.status_file) if args.status_file else DATA_DIR / "crawl_status.json"  # noqa: F841

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = load_status(STATUS_FILE)

    if args.status:
        print_status(status)
        return

    # --retry-failed: crawl_status.json의 failed 건만 slow path로 재시도
    if args.retry_failed:
        failed_vods = {
            vod_id: info
            for vod_id, info in status["vods"].items()
            if info.get("status") == "failed"
        }
        log.info(f"--retry-failed: {len(failed_vods)}건 slow path 재시도 (ytsearch3+600s)")
        TRAILERS_DIR = Path(args.trailers_dir)
        retry_done = 0
        for vod_id, info in failed_vods.items():
            queries = build_search_queries(
                info.get("asset_nm", ""),
                info.get("ct_cl", ""),
                "",                         # genre은 status에 미저장, 쿼리 빌드에 미사용
                info.get("series_nm"),
            )
            result = try_download(vod_id, queries, TRAILERS_DIR, args.dry_run, slow=True)
            result["ct_cl"]            = info.get("ct_cl")
            result["series_nm"]        = info.get("series_nm")
            result["series_key"]       = info.get("series_key")
            result["series_nm_is_bad"] = info.get("series_nm_is_bad")
            result["asset_nm"]         = info.get("asset_nm")
            result["slow_path"]        = True
            status["vods"][vod_id] = result
            if result["status"] == "success":
                status["success"] = status.get("success", 0) + 1
                status["failed"]  = max(0, status.get("failed", 0) - 1)
                log.info(f"OK  {vod_id} ({info.get('asset_nm')}) → {result['filename']}")
            else:
                log.warning(f"FAIL {vod_id} ({info.get('asset_nm')}): {result.get('reason')}")
            retry_done += 1
            if retry_done % BATCH_SAVE_INTERVAL == 0:
                save_status(status, STATUS_FILE)
        save_status(status, STATUS_FILE)
        print_status(status)
        log.info("retry-failed 완료")
        return

    # ── VOD 목록 로드 ────────────────────────────────────────────────────────
    if args.task_file:
        task_path = Path(args.task_file)
        with open(task_path, encoding='utf-8') as f:
            task_data = json.load(f)
        # tasks_missing.json: {"total": N, "tasks": [...]}
        # tasks_X.json:       {"team": "A", "vods": [...]}
        if "tasks" in task_data:
            raw = task_data["tasks"]
            vod_list = [
                {"vod_id": t["vod_id"], "asset_nm": t["asset_nm"],
                 "ct_cl": t["ct_cl"], "genre": t.get("genre", ""),
                 "series_nm": t.get("series_nm"), "provider": t.get("provider")}
                for t in raw
            ]
        else:
            vod_list = task_data.get("vods", [])
        log.info(f"작업 파일 로드: {task_path.name} — {len(vod_list):,}건")

    else:
        log.info("vod 테이블에서 대상 목록 조회 중...")
        try:
            vod_list = fetch_vod_list(ct_cl_filter=args.ct_cl)
        except Exception as e:
            log.error(f"DB 연결 실패: {e}")
            return

        if args.pilot:
            log.info("=== 파일럿 모드: ct_cl 층화 100개 샘플 ===")
            vod_list = stratified_sample(vod_list, total=100)
            status["mode"] = "pilot"
        else:
            series_pool  = [v for v in vod_list if v["ct_cl"] in SERIES_EMBED_CT_CL]
            episode_pool = [v for v in vod_list if v["ct_cl"] in EPISODE_EMBED_CT_CL]
            other_pool   = [v for v in vod_list if v["ct_cl"] not in SERIES_EMBED_CT_CL
                                                 and v["ct_cl"] not in EPISODE_EMBED_CT_CL]
            deduped_series = dedup_by_series_nm(series_pool)
            log.info(f"시리즈 dedup: {len(series_pool):,} → {len(deduped_series):,}건")
            log.info(f"에피소드 단위(TV 연예/오락): {len(episode_pool):,}건")
            vod_list = deduped_series + episode_pool + other_pool

    if args.limit > 0:
        vod_list = vod_list[:args.limit]
        log.info(f"--limit {args.limit} 적용")

    status["total"] = len(vod_list)
    log.info(f"대상 VOD: {len(vod_list):,}개")

    # ── 크롤링 루프 ──────────────────────────────────────────────────────────
    done_count = 0
    for i, vod in enumerate(vod_list):
        vod_id = vod["vod_id"]

        if vod_id in status["vods"] and status["vods"][vod_id]["status"] in ("success", "skipped"):
            continue

        queries = build_search_queries(
            vod["asset_nm"], vod["ct_cl"], vod.get("genre", ""),
            vod.get("series_nm"), vod.get("provider")
        )
        result = try_download(vod_id, queries, TRAILERS_DIR, args.dry_run)

        # fast path 실패 시 slow path fallback (ytsearch3 + 600s)
        if result["status"] == "failed":
            log.info(f"  [slow] {vod_id} ({vod['asset_nm']}) — slow path 재시도")
            result = try_download(vod_id, queries, TRAILERS_DIR, args.dry_run, slow=True)
            if result["status"] == "success":
                result["slow_path"] = True

        # 전파 메타 저장 → ingest_to_db.py --propagate 시 시리즈 전파에 사용
        series_key, is_bad = effective_series_nm(vod.get("series_nm"), vod["asset_nm"])
        result["ct_cl"]            = vod["ct_cl"]
        result["series_nm"]        = vod.get("series_nm")
        result["series_key"]       = series_key
        result["series_nm_is_bad"] = is_bad
        result["asset_nm"]         = vod["asset_nm"]
        result["provider"]         = vod.get("provider")

        status["vods"][vod_id] = result
        status["processed"] = status.get("processed", 0) + 1

        if result["status"] == "success":
            status["success"] = status.get("success", 0) + 1
            dur   = result.get('duration_sec', 0)
            score = result.get('score', '-')
            log.info(f"[{i+1}/{len(vod_list)}] OK   {vod_id} ({vod['asset_nm']}) "
                     f"→ {result['filename']} [{dur}초, score={score}]")
        else:
            status["failed"] = status.get("failed", 0) + 1
            log.warning(f"[{i+1}/{len(vod_list)}] FAIL {vod_id} ({vod['asset_nm']}): "
                        f"{result.get('reason')}")

        done_count += 1
        if done_count % BATCH_SAVE_INTERVAL == 0:
            save_status(status, STATUS_FILE)
            log.info(f"체크포인트 저장 ({done_count}건 처리)")

    save_status(status, STATUS_FILE)
    print_status(status)
    log.info("크롤링 완료")


if __name__ == "__main__":
    main()
