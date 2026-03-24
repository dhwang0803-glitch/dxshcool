"""
포스터 수집 메인 실행 스크립트.

실행:
    python Poster_Collection/scripts/crawl_posters.py              # 전체 실행
    python Poster_Collection/scripts/crawl_posters.py --limit 100  # 테스트용 100건
    python Poster_Collection/scripts/crawl_posters.py --resume     # 체크포인트 재개
"""
import sys
import os
import time
import json
import csv
import math
import argparse
import logging
from datetime import datetime

_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

import psycopg2
from Poster_Collection.src import tmdb_poster, image_downloader
from Poster_Collection.src.tving_poster import parse_season_from_asset_nm

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_MODULE_DIR = os.path.join(_root, "Poster_Collection")
_DATA_DIR = os.path.join(_MODULE_DIR, "data")
MANIFEST_HEADER = ["series_id", "series_nm", "season", "local_path", "poster_url", "downloaded_at"]
CHECKPOINT_INTERVAL = 50
API_SLEEP_BASE = 0.25  # 단일 프로세스 기준 sleep (TMDB: 40req/10s = 4req/s)

# 파트별 파일 경로 (--total-parts > 1이면 _part{N} 접미사)
_part_suffix = ""

def _checkpoint_path():
    return os.path.join(_DATA_DIR, f"crawl_status{_part_suffix}.json")

def _manifest_path():
    return os.path.join(_DATA_DIR, f"manifest{_part_suffix}.csv")


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def fetch_tmdb_migrate_series(conn, rag_source: str = None) -> list[dict]:
    """poster_url이 TMDB URL인 VOD의 (series_nm, season) DISTINCT 목록 조회.

    --tmdb-migrate 모드 전용: TMDB API 재호출 없이 기존 TMDB URL을 직접 다운로드한다.
    """
    with conn.cursor() as cur:
        rag_filter = "AND rag_source = %s" if rag_source else ""
        params = (rag_source,) if rag_source else ()
        cur.execute(
            f"""
            SELECT full_asset_id, series_nm, ct_cl,
                   EXTRACT(YEAR FROM release_date)::int AS release_year,
                   asset_nm, poster_url
            FROM vod
            WHERE poster_url LIKE '%%tmdb.org%%'
              AND series_nm IS NOT NULL
              {rag_filter}
            ORDER BY series_nm, full_asset_id
            """,
            params,
        )
        rows = cur.fetchall()

    seen = set()
    result = []
    for r in rows:
        asset_nm = r[4] or ""
        _, season = parse_season_from_asset_nm(asset_nm) if asset_nm else ("", 1)
        key = (r[1], season)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "series_id": r[0],
            "series_nm": r[1],
            "ct_cl": r[2],
            "release_year": r[3],
            "asset_nm": asset_nm,
            "season": season,
            "existing_poster_url": r[5],
        })
    return result


def fetch_all_series(conn, rag_source: str = None) -> list[dict]:
    """poster_url IS NULL인 (series_nm, season) DISTINCT 목록 조회.

    asset_nm에서 시즌을 파싱하여 (series_nm, season)별로 1건만 반환.
    동일 series_nm이라도 시즌이 다르면 별도 항목으로 처리.
    rag_source 지정 시 해당 값을 가진 VOD만 대상으로 한다.
    """
    with conn.cursor() as cur:
        rag_filter = "AND rag_source = %s" if rag_source else ""
        params = (rag_source,) if rag_source else ()
        cur.execute(
            f"""
            SELECT full_asset_id, series_nm, ct_cl,
                   EXTRACT(YEAR FROM release_date)::int AS release_year,
                   asset_nm
            FROM vod
            WHERE poster_url IS NULL
              AND series_nm IS NOT NULL
              {rag_filter}
            ORDER BY series_nm, full_asset_id
            """,
            params,
        )
        rows = cur.fetchall()

    seen = set()
    result = []
    for r in rows:
        asset_nm = r[4] or ""
        _, season = parse_season_from_asset_nm(asset_nm) if asset_nm else ("", 1)
        key = (r[1], season)  # (series_nm, season)
        if key in seen:
            continue
        seen.add(key)
        result.append({
            "series_id": r[0],
            "series_nm": r[1],
            "ct_cl": r[2],
            "release_year": r[3],
            "asset_nm": asset_nm,
            "season": season,
        })
    return result


def load_processed_ids() -> set:
    """체크포인트에서 이미 처리된 series_id 집합 로드."""
    cp = _checkpoint_path()
    if not os.path.exists(cp):
        return set()
    with open(cp, encoding="utf-8") as f:
        data = json.load(f)
    return set(str(x) for x in data.get("processed_ids", []))


def save_checkpoint(processed_ids: set, stats: dict):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_checkpoint_path(), "w", encoding="utf-8") as f:
        json.dump(
            {
                "processed_ids": list(processed_ids),
                "total_processed": len(processed_ids),
                "stats": stats,
                "last_updated": datetime.now().isoformat(),
            },
            f,
            ensure_ascii=False,
            indent=2,
        )


def append_manifest(rows: list[dict]):
    os.makedirs(_DATA_DIR, exist_ok=True)
    mp = _manifest_path()
    write_header = not os.path.exists(mp)
    with open(mp, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_HEADER, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def run_crawl(series_list: list[dict], local_dir: str, api_sleep: float = API_SLEEP_BASE,
              tmdb_migrate: bool = False) -> dict:
    """series_list 처리. 매 CHECKPOINT_INTERVAL건마다 체크포인트·매니페스트 저장.

    tmdb_migrate=True 이면 TMDB API 호출 없이 item['existing_poster_url']을 직접 사용.
    """
    processed_ids: set = set()
    pending_manifest: list[dict] = []
    stats = {"total": 0, "api_ok": 0, "dl_ok": 0, "api_fail": 0, "dl_fail": 0}
    total = len(series_list)

    for idx, item in enumerate(series_list, 1):
        sid = item["series_id"]
        snm = item["series_nm"]
        season = item.get("season", 1)

        if tmdb_migrate:
            # TMDB API 재호출 없이 DB에 저장된 TMDB URL 직접 사용
            image_url = item.get("existing_poster_url")
            if not image_url:
                logger.info("[%d/%d] sid=%-12s ✗ 기존 URL 없음 %s", idx, total, sid, snm)
                stats["api_fail"] += 1
                stats["total"] += 1
                processed_ids.add(str(sid))
                continue
            stats["api_ok"] += 1
            logger.info("[%d/%d] sid=%-12s ✓ migrate %s (시즌%d)", idx, total, sid, snm, season)
        else:
            # TMDB 포스터 — fetch_all_series에서 이미 시즌 파싱 완료
            ct_cl = item.get("ct_cl")
            try:
                result = tmdb_poster.search(snm, season=season, ct_cl=ct_cl, sleep=api_sleep)
            except Exception as e:
                logger.error("[%d/%d] API 오류 sid=%s: %s", idx, total, sid, e)
                stats["api_fail"] += 1
                stats["total"] += 1
                processed_ids.add(str(sid))
                continue

            if not result:
                logger.info("[%d/%d] sid=%-12s ✗ TMDB 미매칭 %s", idx, total, sid, snm)
                stats["api_fail"] += 1
                stats["total"] += 1
                processed_ids.add(str(sid))
                continue

            stats["api_ok"] += 1
            image_url = result["image_url"]
            matched = result.get("matched_name", "")
            mtype = result.get("media_type", "?")
            marker = "S" if result.get("season_matched") else "FB"
            logger.info("[%d/%d] sid=%-12s ✓ %s → %s (%s/시즌%d/%s)", idx, total, sid, snm, matched, mtype, season, marker)

        # 이미지 다운로드
        local_path = image_downloader.download(sid, image_url, local_dir)
        if local_path:
            stats["dl_ok"] += 1
            logger.info("         → 저장 %s", local_path)
        else:
            stats["dl_fail"] += 1
            logger.warning("         → 다운로드 실패 sid=%s", sid)

        pending_manifest.append(
            {
                "series_id": sid,
                "series_nm": snm,
                "season": season,
                "local_path": local_path or "",
                "poster_url": image_url,
                "downloaded_at": datetime.now().strftime("%Y-%m-%d"),
            }
        )
        processed_ids.add(str(sid))
        stats["total"] += 1

        if idx % CHECKPOINT_INTERVAL == 0:
            append_manifest(pending_manifest)
            pending_manifest.clear()
            save_checkpoint(processed_ids, stats)
            logger.info(
                "=== 체크포인트 저장 [%d/%d] API %.0f%% / DL %.0f%% ===",
                idx,
                total,
                stats["api_ok"] / stats["total"] * 100 if stats["total"] else 0,
                stats["dl_ok"] / stats["api_ok"] * 100 if stats["api_ok"] else 0,
            )

    # 잔여 flush
    if pending_manifest:
        append_manifest(pending_manifest)
    save_checkpoint(processed_ids, stats)
    return stats


def main():
    parser = argparse.ArgumentParser(description="포스터 수집 메인 스크립트")
    parser.add_argument("--limit", type=int, default=0, help="처리 건수 제한 (0=전체)")
    parser.add_argument("--resume", action="store_true", help="체크포인트에서 재개")
    parser.add_argument("--part", type=int, default=1, help="분할 번호 (1-based, 기본: 1)")
    parser.add_argument("--total-parts", type=int, default=1, help="총 분할 수 (기본: 1=단일)")
    parser.add_argument("--ct-cl", type=str, default=None, help="ct_cl 필터 (예: 'TV연예/오락')")
    parser.add_argument("--rag-source", type=str, default=None, help="rag_source 필터 (예: TMDB_NEW_2025)")
    parser.add_argument("--tmdb-migrate", action="store_true",
                        help="TMDB URL이 있는 VOD를 OCI로 마이그레이션 (API 재호출 없이 기존 URL 사용)")
    args = parser.parse_args()

    if args.part < 1 or args.part > args.total_parts:
        logger.error("--part는 1 이상 --total-parts 이하여야 합니다.")
        sys.exit(1)

    # 파트별 manifest/checkpoint 파일 분리 (1분할 포함 항상 적용)
    global _part_suffix
    _part_suffix = f"_part{args.part}"

    local_dir = os.getenv("LOCAL_POSTER_DIR")
    if not local_dir:
        logger.error("LOCAL_POSTER_DIR 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    logger.info("DB 연결 중...")
    conn = get_db_conn()
    rag_source = getattr(args, 'rag_source', None)
    tmdb_migrate = getattr(args, 'tmdb_migrate', False)
    if tmdb_migrate:
        logger.info("시리즈 목록 조회 중 (TMDB migrate%s)...",
                    f", rag_source={rag_source}" if rag_source else "")
        all_series = fetch_tmdb_migrate_series(conn, rag_source=rag_source)
    else:
        logger.info("시리즈 목록 조회 중 (poster_url IS NULL%s)...",
                    f", rag_source={rag_source}" if rag_source else "")
        all_series = fetch_all_series(conn, rag_source=rag_source)
    conn.close()
    logger.info("DB 조회 완료: %d건", len(all_series))

    if args.ct_cl:
        all_series = [s for s in all_series if s.get("ct_cl") == args.ct_cl]
        logger.info("ct_cl 필터 '%s' 적용 → %d건", args.ct_cl, len(all_series))

    if args.resume:
        processed_ids = load_processed_ids()
        all_series = [s for s in all_series if str(s["series_id"]) not in processed_ids]
        logger.info("재개 모드: 처리 완료 %d건 스킵, 남은 %d건", len(processed_ids), len(all_series))

    # 분할 슬라이싱
    if args.total_parts > 1:
        chunk = math.ceil(len(all_series) / args.total_parts)
        start = (args.part - 1) * chunk
        series_list = all_series[start: start + chunk]
        logger.info("분할 %d/%d: %d건 담당 (전체 %d건)", args.part, args.total_parts, len(series_list), len(all_series))
    else:
        series_list = all_series

    if args.limit:
        series_list = series_list[: args.limit]
        logger.info("--limit %d 적용 → %d건 처리", args.limit, len(series_list))

    if not series_list:
        logger.info("처리할 시리즈가 없습니다.")
        sys.exit(0)

    # 병렬 실행 시 sleep을 total_parts 배로 늘려 초당 10건 한도 유지
    api_sleep = API_SLEEP_BASE * args.total_parts

    logger.info("크롤링 시작: %d건 (저장: %s, sleep=%.2fs)", len(series_list), local_dir, api_sleep)
    t_start = time.time()
    stats = run_crawl(series_list, local_dir, api_sleep=api_sleep, tmdb_migrate=tmdb_migrate)
    elapsed = time.time() - t_start

    total = stats["total"]
    logger.info(
        "완료: %d건 / API 성공 %d (%.1f%%) / 다운로드 성공 %d (%.1f%%) / 소요 %.1f분",
        total,
        stats["api_ok"],
        stats["api_ok"] / total * 100 if total else 0,
        stats["dl_ok"],
        stats["dl_ok"] / stats["api_ok"] * 100 if stats["api_ok"] else 0,
        elapsed / 60,
    )
    logger.info("매니페스트: %s", _manifest_path())
    logger.info("체크포인트: %s", _checkpoint_path())


if __name__ == "__main__":
    main()
