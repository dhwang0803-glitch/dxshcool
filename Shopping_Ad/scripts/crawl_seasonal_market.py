"""
crawl_seasonal_market.py — LG헬로비전 제철장터 편성표 크롤링

LG헬로비전 편성표 API에서 "제철장터" 프로그램을 필터링하여
상품명, 방송시간을 수집한다.

실행:
    cd Shopping_Ad
    python scripts/crawl_seasonal_market.py
    python scripts/crawl_seasonal_market.py --date 2026-04-11
    python scripts/crawl_seasonal_market.py --days 7          # 오늘부터 7일간
    python scripts/crawl_seasonal_market.py --dry-run
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

AJAX_URL = "https://ch.lghellovision.net/main/mainScheduleListAjax.do"
SO_CODE = "SC40000000"


def crawl_date(target_date):
    """특정 날짜의 제철장터 편성표 크롤링"""
    date_compact = target_date.replace("-", "")

    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://ch.lghellovision.net/main/mainScheduleList.do",
    }
    data = {
        "soCode": SO_CODE,
        "startdate": date_compact,
    }

    try:
        resp = requests.post(AJAX_URL, headers=headers, data=data, timeout=15)
        resp.raise_for_status()
        result = resp.json()
    except Exception as e:
        print(f"  ❌ {target_date} 크롤링 실패: {e}")
        return []

    schedule_list = result.get("scheduleList", [])
    products = []

    for item in schedule_list:
        title = item.get("TITLE", "")
        if "제철장터" not in title:
            continue

        subtitle = (item.get("SUBTITLE") or "").strip()
        if not subtitle:
            continue

        sh = item.get("START_HOUR", "")
        sm = item.get("START_MINUTE", "")
        eh = item.get("END_HOUR", "")
        em = item.get("END_MINUTE", "")

        start_time = f"{sh}:{sm}" if sh and sm else None
        end_time = f"{eh}:{em}" if eh and em else None

        products.append({
            "channel": "제철장터",
            "broadcast_date": target_date,
            "start_time": start_time,
            "end_time": end_time,
            "product_name": subtitle,
        })

    return products


def main():
    parser = argparse.ArgumentParser(description="LG헬로비전 제철장터 편성표 크롤링")
    parser.add_argument("--date", type=str, default=None, help="특정 날짜 (YYYY-MM-DD)")
    parser.add_argument("--days", type=int, default=7, help="오늘부터 N일간 (기본 7)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"  LG헬로비전 제철장터 편성표 크롤링")
    print(f"{'=' * 60}")

    if args.date:
        dates = [args.date]
    else:
        today = datetime.now()
        dates = [(today + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(args.days)]

    print(f"  대상: {dates[0]} ~ {dates[-1]} ({len(dates)}일)")

    all_products = []
    for d in dates:
        products = crawl_date(d)
        all_products.extend(products)
        if products:
            print(f"  {d}: {len(products)}건")
        else:
            print(f"  {d}: 0건")

    print(f"\n  총 {len(all_products)}건")

    if not all_products:
        print(f"  ⚠️ 제철장터 편성 없음")
        return

    # 상품 목록 출력
    print(f"\n  편성표:")
    for p in all_products:
        print(f"    {p['broadcast_date']} {p['start_time']}~{p['end_time']} | {p['product_name']}")

    if args.dry_run:
        print(f"\n  [DRY-RUN] 파일 저장 안 함")
        return

    # JSON 저장
    json_path = OUTPUT_DIR / "seasonal_market.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_products, f, ensure_ascii=False, indent=2)
    print(f"\n  저장: {json_path}")

    # 상품명 → 카테고리 매핑 yaml 생성
    product_set = sorted(set(p["product_name"] for p in all_products))
    yaml_path = OUTPUT_DIR / "seasonal_market_products.yaml"
    with open(yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(product_set, f, allow_unicode=True, default_flow_style=False)
    print(f"  저장: {yaml_path} ({len(product_set)}개 상품)")


if __name__ == "__main__":
    main()
