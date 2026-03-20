"""
crawl_festivals.py — Visit Korea 축제 정보 크롤링

한국관광공사 API에서 4~5월 축제 목록을 수집하여
region 기반 광고 매칭에 사용할 축제 데이터를 생성한다.

실행:
    cd Shopping_Ad
    python scripts/crawl_festivals.py
    python scripts/crawl_festivals.py --month 4        # 4월만
    python scripts/crawl_festivals.py --month 4 5      # 4~5월
    python scripts/crawl_festivals.py --dry-run         # 결과 출력만
"""
import sys
import json
import argparse
import re
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import requests
import yaml

PROJECT_ROOT = Path(__file__).parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

API_URL = "https://korean.visitkorea.or.kr/kfes/list/selectWntyFstvlList.do"


def fetch_month(month, max_pages=10):
    """특정 월 축제 전체 페이지 수집 (form-urlencoded)"""
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://korean.visitkorea.or.kr/kfes/list/wntyFstvlList.do",
        "X-Requested-With": "XMLHttpRequest",
    }
    all_items = []
    for page in range(max_pages):
        data = {
            "startIdx": str(page * 12),
            "searchType": "A",
            "searchDate": f"{month:02d}월",
        }
        try:
            resp = requests.post(API_URL, headers=headers, data=data, timeout=30)
            resp.raise_for_status()
            items = resp.json().get("resultList", [])
            if not items:
                break
            all_items.extend(items)
            print(f"    페이지 {page+1}: {len(items)}건 (누적 {len(all_items)}건)")
            if len(items) < 12:
                break
        except Exception as e:
            print(f"    페이지 {page+1} 실패: {e}")
            break
    return all_items


def parse_region(area_nm):
    """
    '전라남도 구례군' → '구례'
    '서울 중구' → '서울'  (구 단위는 상위 시/도로)
    '부산 해운대구' → '부산'
    '경기도 가평군' → '가평'
    """
    if not area_nm:
        return None
    parts = area_nm.split()
    if len(parts) < 2:
        return re.sub(r"(특별자치시|특별자치도|특별시|광역시)$", "", area_nm)

    last = parts[-1]
    # "구"로 끝나면 → 상위 시/도 사용 (서울 중구 → 서울, 부산 해운대구 → 부산)
    if last.endswith("구"):
        first = parts[0]
        return re.sub(r"(특별자치시|특별자치도|특별시|광역시)$", "", first)
    # "시"나 "군"으로 끝나면 → 해당 시/군 사용 (경기도 가평군 → 가평)
    return re.sub(r"(시|군)$", "", last)


def to_record(raw):
    """API 응답 → 정제된 축제 레코드"""
    return {
        "festival_name": raw.get("cntntsNm", "").strip(),
        "region": parse_region(raw.get("areaNm", "")),
        "region_full": raw.get("areaNm", "").strip(),
        "address": (raw.get("adres") or "").strip(),
        "start_date": raw.get("fstvlBgngDe", ""),
        "end_date": raw.get("fstvlEndDe", ""),
        "description": (raw.get("fstvlOutlCn") or "").strip(),
        "fee": (raw.get("fstvlUtztFareInfo") or "").strip(),
        "organizer": (raw.get("fstvlAspcsNm") or "").strip(),
        "homepage": (raw.get("fstvlHmpgUrl") or "").strip(),
        "image_url": raw.get("dispFstvlCntntsImgRout", ""),
        "status": "진행중" if raw.get("fstvlIngFlag") == "1" else "예정",
    }


def main():
    parser = argparse.ArgumentParser(description="Visit Korea 축제 크롤링")
    parser.add_argument("--month", nargs="+", type=int, default=[4, 5])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR / "festivals.json"))
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"  Visit Korea 축제 크롤링")
    print(f"  대상 월: {args.month}")
    print(f"{'=' * 60}")

    all_raw = []
    for m in args.month:
        print(f"\n  [{m}월] 조회 중...")
        raw = fetch_month(m)
        all_raw.extend(raw)
        print(f"  → {m}월: {len(raw)}건")

    # 중복 제거
    seen = set()
    unique = []
    for r in all_raw:
        key = (r.get("cntntsNm", ""), r.get("fstvlBgngDe", ""))
        if key not in seen:
            seen.add(key)
            unique.append(r)

    festivals = [to_record(r) for r in unique]
    # 2026년만 필터
    festivals = [f for f in festivals if f["start_date"].startswith("2026")]
    print(f"\n  총 축제 (2026년, 중복 제거): {len(festivals)}건")

    # 지역별 분포
    regions = {}
    for f in festivals:
        r = f["region"] or "기타"
        regions[r] = regions.get(r, 0) + 1

    print(f"\n  지역별 분포:")
    for region, cnt in sorted(regions.items(), key=lambda x: -x[1])[:30]:
        print(f"    {region}: {cnt}건")

    print(f"\n  축제 목록:")
    for f in festivals:
        print(f"    [{f['status']}] {f['festival_name']} | {f['region_full']} | {f['start_date']}~{f['end_date']}")

    if args.dry_run:
        print(f"\n  [DRY-RUN] 파일 저장 안 함")
        return

    # JSON 저장
    with open(args.output, "w", encoding="utf-8") as fp:
        json.dump(festivals, fp, ensure_ascii=False, indent=2)
    print(f"\n  저장: {args.output} ({len(festivals)}건)")

    # region→festival yaml
    region_map = {}
    for f in festivals:
        r = f["region"]
        if not r:
            continue
        if r not in region_map:
            region_map[r] = []
        region_map[r].append({
            "name": f["festival_name"],
            "period": f"{f['start_date']}~{f['end_date']}",
        })

    yaml_path = OUTPUT_DIR / "region_festivals.yaml"
    with open(yaml_path, "w", encoding="utf-8") as fp:
        yaml.dump(region_map, fp, allow_unicode=True, default_flow_style=False, sort_keys=False)
    print(f"  저장: {yaml_path} ({len(region_map)}개 지역)")


if __name__ == "__main__":
    main()
