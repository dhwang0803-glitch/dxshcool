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
CHECKPOINT_PATH = os.path.join(_DATA_DIR, "crawl_status.json")
MANIFEST_PATH = os.path.join(_DATA_DIR, "manifest.csv")
MANIFEST_HEADER = ["series_id", "series_nm", "local_path", "poster_url", "downloaded_at"]
CHECKPOINT_INTERVAL = 50
API_SLEEP_BASE = 0.25  # 단일 프로세스 기준 sleep (TMDB: 40req/10s = 4req/s)


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def fetch_all_series(conn) -> list[dict]:
    """poster_url IS NULL인 series_nm DISTINCT 목록 조회 (ct_cl, release_year, asset_nm 포함)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (series_nm)
                full_asset_id, series_nm, ct_cl,
                EXTRACT(YEAR FROM release_date)::int AS release_year,
                asset_nm
            FROM vod
            WHERE poster_url IS NULL
              AND series_nm IS NOT NULL
            ORDER BY series_nm, full_asset_id
            """
        )
        rows = cur.fetchall()
    return [
        {
            "series_id": r[0],
            "series_nm": r[1],
            "ct_cl": r[2],
            "release_year": r[3],
            "asset_nm": r[4],
        }
        for r in rows
    ]


def load_processed_ids() -> set:
    """체크포인트에서 이미 처리된 series_id 집합 로드."""
    if not os.path.exists(CHECKPOINT_PATH):
        return set()
    with open(CHECKPOINT_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return set(str(x) for x in data.get("processed_ids", []))


def save_checkpoint(processed_ids: set, stats: dict):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(CHECKPOINT_PATH, "w", encoding="utf-8") as f:
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
    write_header = not os.path.exists(MANIFEST_PATH)
    with open(MANIFEST_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANIFEST_HEADER, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerows(rows)


def run_crawl(series_list: list[dict], local_dir: str, api_sleep: float = API_SLEEP_BASE) -> dict:
    """series_list 처리. 매 CHECKPOINT_INTERVAL건마다 체크포인트·매니페스트 저장."""
    processed_ids: set = set()
    pending_manifest: list[dict] = []
    stats = {"total": 0, "api_ok": 0, "dl_ok": 0, "api_fail": 0, "dl_fail": 0}
    total = len(series_list)

    for idx, item in enumerate(series_list, 1):
        sid = item["series_id"]
        snm = item["series_nm"]

        # TMDB 포스터 — asset_nm에서 시즌 파싱
        ct_cl = item.get("ct_cl")
        asset_nm = item.get("asset_nm") or ""
        _, season = parse_season_from_asset_nm(asset_nm) if asset_nm else (snm, 1)
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
        marker = "S" if result.get("season_matched") else "FB"
        logger.info("[%d/%d] sid=%-12s ✓ %s → %s (시즌%d/%s)", idx, total, sid, snm, matched, season, marker)

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
    args = parser.parse_args()

    if args.part < 1 or args.part > args.total_parts:
        logger.error("--part는 1 이상 --total-parts 이하여야 합니다.")
        sys.exit(1)

    local_dir = os.getenv("LOCAL_POSTER_DIR")
    if not local_dir:
        logger.error("LOCAL_POSTER_DIR 환경변수가 설정되지 않았습니다.")
        sys.exit(1)

    logger.info("DB 연결 중...")
    conn = get_db_conn()
    logger.info("시리즈 목록 조회 중 (poster_url IS NULL)...")
    all_series = fetch_all_series(conn)
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
    stats = run_crawl(series_list, local_dir, api_sleep=api_sleep)
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
    logger.info("매니페스트: %s", MANIFEST_PATH)
    logger.info("체크포인트: %s", CHECKPOINT_PATH)


if __name__ == "__main__":
    main()
