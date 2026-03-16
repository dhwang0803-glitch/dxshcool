"""
TMDB 시즌별 포스터 파일럿 테스트.

DB에서 poster_url IS NULL인 항목 중 TV연예/오락 50건, 드라마 50건을 대상으로
TMDB 시즌별 포스터 수집을 테스트한다.

실행:
    python Poster_Collection/scripts/pilot_tmdb.py
    python Poster_Collection/scripts/pilot_tmdb.py --limit 20   # 카테고리당 20건
    python Poster_Collection/scripts/pilot_tmdb.py --download    # 이미지 다운로드까지
"""
import sys
import os
import argparse
import logging
import json
import time
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
PILOT_REPORT_PATH = os.path.join(_DATA_DIR, "pilot_tmdb_report.json")


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def fetch_pilot_series(conn, ct_cl: str, limit: int) -> list[dict]:
    """poster_url IS NULL인 항목 중 ct_cl 필터링하여 limit건 조회."""
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
              AND ct_cl = %s
            ORDER BY series_nm, full_asset_id
            LIMIT %s
            """,
            (ct_cl, limit),
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


def run_pilot(series_list: list[dict], do_download: bool, local_dir: str) -> list[dict]:
    """파일럿 실행. 각 항목의 결과를 반환."""
    results = []
    total = len(series_list)

    for idx, item in enumerate(series_list, 1):
        sid = item["series_id"]
        snm = item["series_nm"]
        ct_cl = item.get("ct_cl", "")
        asset_nm = item.get("asset_nm") or ""

        # asset_nm에서 시즌 파싱
        _, season = parse_season_from_asset_nm(asset_nm) if asset_nm else (snm, 1)

        t0 = time.time()
        try:
            result = tmdb_poster.search(snm, season=season, ct_cl=ct_cl, sleep=0.3)
        except Exception as e:
            logger.error("[%d/%d] API 오류 sid=%s: %s", idx, total, sid, e)
            results.append({
                "series_id": sid, "series_nm": snm, "ct_cl": ct_cl,
                "asset_nm": asset_nm, "season": season,
                "status": "ERROR", "error": str(e),
            })
            continue
        elapsed = time.time() - t0

        if not result:
            logger.info(
                "[%d/%d] ✗ %-20s (시즌%d) — TMDB 미매칭",
                idx, total, snm[:20], season,
            )
            results.append({
                "series_id": sid, "series_nm": snm, "ct_cl": ct_cl,
                "asset_nm": asset_nm, "season": season,
                "status": "NOT_FOUND", "elapsed": round(elapsed, 2),
            })
            continue

        # 매칭 성공
        tmdb_id = result.get("tmdb_id")
        matched = result.get("matched_name", "")
        season_matched = result.get("season_matched", False)
        image_url = result["image_url"]

        marker = "S" if season_matched else "F"  # S=시즌포스터, F=시리즈fallback
        logger.info(
            "[%d/%d] ✓ %-20s → %-20s (시즌%d/%s) tmdb=%s",
            idx, total, snm[:20], matched[:20], season, marker, tmdb_id,
        )

        entry = {
            "series_id": sid, "series_nm": snm, "ct_cl": ct_cl,
            "asset_nm": asset_nm, "season": season,
            "status": "OK",
            "tmdb_id": tmdb_id,
            "matched_name": matched,
            "season_matched": season_matched,
            "image_url": image_url,
            "elapsed": round(elapsed, 2),
        }

        # 선택: 이미지 다운로드
        if do_download and local_dir:
            local_path = image_downloader.download(sid, image_url, local_dir)
            entry["local_path"] = local_path or ""
            entry["download_ok"] = local_path is not None

        results.append(entry)

    return results


def print_summary(results: list[dict], label: str):
    """카테고리별 요약 출력."""
    total = len(results)
    ok = sum(1 for r in results if r["status"] == "OK")
    not_found = sum(1 for r in results if r["status"] == "NOT_FOUND")
    errors = sum(1 for r in results if r["status"] == "ERROR")
    season_matched = sum(1 for r in results if r.get("season_matched"))
    fallback = ok - season_matched

    logger.info("=" * 60)
    logger.info("[%s] 파일럿 결과", label)
    logger.info("-" * 60)
    logger.info("  총 대상:      %d건", total)
    logger.info("  TMDB 매칭:    %d건 (%.1f%%)", ok, ok / total * 100 if total else 0)
    logger.info("    시즌 포스터: %d건", season_matched)
    logger.info("    시리즈 FB:  %d건", fallback)
    logger.info("  미매칭:       %d건", not_found)
    logger.info("  오류:         %d건", errors)
    logger.info("=" * 60)

    # 미매칭 목록 출력
    if not_found > 0:
        logger.info("미매칭 목록:")
        for r in results:
            if r["status"] == "NOT_FOUND":
                logger.info("  - %s (시즌%d)", r["series_nm"], r["season"])


def main():
    parser = argparse.ArgumentParser(description="TMDB 시즌별 포스터 파일럿")
    parser.add_argument("--limit", type=int, default=50, help="카테고리당 건수 (기본: 50)")
    parser.add_argument("--download", action="store_true", help="이미지 다운로드까지 수행")
    args = parser.parse_args()

    local_dir = os.getenv("LOCAL_POSTER_DIR", "")

    if args.download and not local_dir:
        logger.error("--download 사용 시 LOCAL_POSTER_DIR 환경변수 필요")
        sys.exit(1)

    logger.info("DB 연결 중...")
    conn = get_db_conn()

    # TV연예/오락 + 드라마 각각 조회
    categories = [
        ("TV 연예/오락", args.limit),
        ("TV드라마", args.limit),
    ]

    all_results = {}
    for ct_cl, limit in categories:
        logger.info("'%s' 조회 중 (limit=%d)...", ct_cl, limit)
        series_list = fetch_pilot_series(conn, ct_cl, limit)
        logger.info("'%s' 조회 완료: %d건", ct_cl, len(series_list))

        if not series_list:
            logger.warning("'%s' 대상 없음 — 스킵", ct_cl)
            continue

        results = run_pilot(series_list, args.download, local_dir)
        all_results[ct_cl] = results
        print_summary(results, ct_cl)

    conn.close()

    # 전체 요약
    total_all = sum(len(v) for v in all_results.values())
    ok_all = sum(1 for v in all_results.values() for r in v if r["status"] == "OK")
    logger.info("")
    logger.info("=== 전체 요약: %d/%d 매칭 (%.1f%%) ===",
                ok_all, total_all, ok_all / total_all * 100 if total_all else 0)

    # 리포트 저장
    os.makedirs(_DATA_DIR, exist_ok=True)
    report = {
        "run_at": datetime.now().isoformat(),
        "config": {"limit_per_category": args.limit, "download": args.download},
        "summary": {
            "total": total_all,
            "ok": ok_all,
            "ok_pct": round(ok_all / total_all * 100, 1) if total_all else 0,
        },
        "categories": {},
    }
    for ct_cl, results in all_results.items():
        ok = sum(1 for r in results if r["status"] == "OK")
        season_matched = sum(1 for r in results if r.get("season_matched"))
        report["categories"][ct_cl] = {
            "total": len(results),
            "ok": ok,
            "season_matched": season_matched,
            "fallback": ok - season_matched,
            "not_found": sum(1 for r in results if r["status"] == "NOT_FOUND"),
            "items": results,
        }

    with open(PILOT_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("리포트 저장 → %s", PILOT_REPORT_PATH)


if __name__ == "__main__":
    main()
