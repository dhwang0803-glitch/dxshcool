"""
파일럿 테스트 — 속도·수집률 측정.

실행:
    python Poster_Collection/scripts/pilot_test.py --limit 50
    python Poster_Collection/scripts/pilot_test.py --limit 50 --no-download  # API만 테스트
    python Poster_Collection/scripts/pilot_test.py --limit 50 --save-report  # reports/ 에 저장

결과 지표:
    - Naver API 성공률 (URL 획득 비율)
    - 이미지 다운로드 성공률
    - 처리 속도 (건/분, 초/건)
    - portrait 이미지 비율
"""
import sys
import os
import time
import json
import argparse
import logging
from datetime import datetime

# 프로젝트 루트를 sys.path에 추가
_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _root)

from dotenv import load_dotenv
load_dotenv()

import psycopg2
from Poster_Collection.src import naver_poster, image_downloader

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def get_db_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )


def fetch_sample_series(conn, limit: int) -> list[dict]:
    """poster_url IS NULL 시리즈에서 limit건 샘플링 (DISTINCT series_nm 기준)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (series_nm) full_asset_id, series_nm
            FROM vod
            WHERE poster_url IS NULL
              AND series_nm IS NOT NULL
            ORDER BY series_nm, full_asset_id
            LIMIT %s
            """,
            (limit,),
        )
        rows = cur.fetchall()
    return [{"series_id": r[0], "series_nm": r[1]} for r in rows]


def run_pilot(series_list: list[dict], local_dir: str, download_images: bool) -> list[dict]:
    results = []
    total = len(series_list)

    for idx, item in enumerate(series_list, 1):
        sid = item["series_id"]
        snm = item["series_nm"]
        row = {"series_id": sid, "series_nm": snm, "api_ok": False, "dl_ok": False,
               "portrait": False, "api_sec": 0.0, "dl_sec": 0.0, "image_url": None,
               "local_path": None, "error": None}

        # --- Naver API ---
        t0 = time.time()
        try:
            result = naver_poster.search(snm)
        except Exception as e:
            row["error"] = str(e)
            results.append(row)
            logger.error("[%d/%d] API 오류 sid=%s: %s", idx, total, sid, e)
            continue

        row["api_sec"] = round(time.time() - t0, 3)

        if result:
            row["api_ok"] = True
            row["image_url"] = result["image_url"]
            if result["height"] > result["width"] > 0:
                row["portrait"] = True
            logger.info("[%d/%d] sid=%-6s ✓ API %.2fs %s",
                        idx, total, sid, row["api_sec"],
                        "(portrait)" if row["portrait"] else "")
        else:
            logger.info("[%d/%d] sid=%-6s ✗ API %.2fs (URL 없음)",
                        idx, total, sid, row["api_sec"])

        # --- 이미지 다운로드 ---
        if download_images and row["api_ok"]:
            t1 = time.time()
            local_path = image_downloader.download(sid, row["image_url"], local_dir)
            row["dl_sec"] = round(time.time() - t1, 3)
            if local_path:
                row["dl_ok"] = True
                row["local_path"] = local_path
                logger.info("         → 저장 %.2fs %s", row["dl_sec"], local_path)
            else:
                logger.warning("         → 다운로드 실패 %.2fs", row["dl_sec"])

        results.append(row)

    return results


def print_report(results: list[dict], elapsed_total: float, download_images: bool):
    total = len(results)
    api_ok = sum(1 for r in results if r["api_ok"])
    dl_ok  = sum(1 for r in results if r["dl_ok"])
    portrait = sum(1 for r in results if r["portrait"])
    errors = sum(1 for r in results if r["error"])

    avg_api = sum(r["api_sec"] for r in results) / total if total else 0
    avg_dl  = (sum(r["dl_sec"] for r in results if r["dl_ok"]) / dl_ok) if dl_ok else 0
    per_item = elapsed_total / total if total else 0
    speed_per_min = 60 / per_item if per_item > 0 else 0

    print("\n" + "=" * 60)
    print("  PILOT TEST 결과")
    print("=" * 60)
    print(f"  처리 건수          : {total}")
    print(f"  총 소요 시간       : {elapsed_total:.1f}초 ({elapsed_total/60:.1f}분)")
    print(f"  처리 속도          : {per_item:.2f}초/건  ({speed_per_min:.0f}건/분)")
    print()
    print(f"  [Naver API]")
    print(f"    성공률           : {api_ok}/{total} = {api_ok/total*100:.1f}%")
    print(f"    평균 응답시간    : {avg_api:.3f}초/건")
    print(f"    portrait 비율    : {portrait}/{api_ok} = {portrait/api_ok*100:.1f}%" if api_ok else "    portrait 비율    : -")
    print(f"    오류 건수        : {errors}")
    if download_images:
        print()
        print(f"  [이미지 다운로드]")
        print(f"    성공률           : {dl_ok}/{api_ok} = {dl_ok/api_ok*100:.1f}%" if api_ok else "    성공률           : -")
        print(f"    평균 다운로드시간: {avg_dl:.3f}초/건")
    print()

    # 전체 규모 추정
    estimated_series = 20000
    est_hours = (per_item * estimated_series) / 3600
    print(f"  [전체 규모 추정 (약 {estimated_series:,}건 기준)]")
    print(f"    예상 소요 시간   : {est_hours:.1f}시간 ({est_hours/24:.1f}일)")
    print(f"    예상 수집 건수   : {api_ok/total*estimated_series:.0f}건 ({api_ok/total*100:.1f}%)" if total else "    -")
    print("=" * 60)

    return {
        "total": total, "api_ok": api_ok, "dl_ok": dl_ok, "portrait": portrait,
        "errors": errors, "elapsed_sec": round(elapsed_total, 2),
        "sec_per_item": round(per_item, 3), "items_per_min": round(speed_per_min, 1),
        "avg_api_sec": round(avg_api, 3), "avg_dl_sec": round(avg_dl, 3),
        "api_success_rate": round(api_ok/total, 4) if total else 0,
        "dl_success_rate": round(dl_ok/api_ok, 4) if api_ok else 0,
        "portrait_rate": round(portrait/api_ok, 4) if api_ok else 0,
    }


def save_report(summary: dict, results: list[dict], report_dir: str):
    os.makedirs(report_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(report_dir, f"pilot_01_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "items": results}, f, ensure_ascii=False, indent=2)
    logger.info("리포트 저장: %s", path)
    return path


def main():
    parser = argparse.ArgumentParser(description="Poster_Collection 파일럿 테스트")
    parser.add_argument("--limit", type=int, default=50, help="테스트 건수 (기본 50)")
    parser.add_argument("--no-download", action="store_true", help="이미지 다운로드 생략 (API만 테스트)")
    parser.add_argument("--save-report", action="store_true", help="결과를 reports/에 JSON으로 저장")
    args = parser.parse_args()

    local_dir = os.getenv("LOCAL_POSTER_DIR")
    download_images = not args.no_download

    if download_images and not local_dir:
        logger.error("LOCAL_POSTER_DIR 환경변수가 설정되지 않았습니다. --no-download 옵션을 사용하거나 .env에 설정하세요.")
        sys.exit(1)

    logger.info("DB 연결 중...")
    conn = get_db_conn()

    logger.info("샘플 %d건 조회 중...", args.limit)
    series_list = fetch_sample_series(conn, args.limit)
    conn.close()

    if not series_list:
        logger.error("poster_url IS NULL 인 시리즈가 없습니다.")
        sys.exit(1)

    logger.info("%d건 처리 시작 (download=%s)", len(series_list), download_images)
    t_start = time.time()
    results = run_pilot(series_list, local_dir or "", download_images)
    elapsed = time.time() - t_start

    summary = print_report(results, elapsed, download_images)

    if args.save_report:
        report_dir = os.path.join(_root, "Poster_Collection", "reports")
        save_report(summary, results, report_dir)


if __name__ == "__main__":
    main()
