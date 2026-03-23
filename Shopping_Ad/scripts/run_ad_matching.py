"""
run_ad_matching.py — VOD 요약 → 축제 + 제철장터 통합 매칭

vod_ad_summary.parquet + STT parquet을 읽어서:
  - 관광지 → region_festivals.yaml 축제 매칭 → local_gov_popup
  - 음식 → seasonal_market.json 실제 상품 매칭 → seasonal_market
결과를 shopping_ad_candidates.parquet으로 저장.

실행:
    cd Shopping_Ad
    python scripts/run_ad_matching.py
"""
import sys
import json
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from festival_matcher import FestivalMatcher
from seasonal_matcher import SeasonalMatcher

DATA_DIR = PROJECT_ROOT / "data"
PARQUET_DIR = PROJECT_ROOT.parent / "Object_Detection" / "data" / "parquet_output"


def load_stt_keywords(parquet_dir):
    """STT parquet에서 VOD별 음식 키워드 수집"""
    stt_path = parquet_dir / "vod_stt_concept.parquet"
    if not stt_path.exists():
        return {}

    df = pd.read_parquet(str(stt_path))
    df_food = df[df["ad_category"] == "음식"]

    vod_keywords = {}
    for vod_id, group in df_food.groupby("vod_id"):
        keywords = list(group["keyword"].value_counts().head(10).index)
        vod_keywords[vod_id] = keywords
    return vod_keywords


def main():
    parser = argparse.ArgumentParser(description="축제 + 제철장터 통합 매칭")
    parser.add_argument("--summary", type=str, default=str(DATA_DIR / "vod_ad_summary.parquet"))
    parser.add_argument("--festivals", type=str, default=str(DATA_DIR / "region_festivals.yaml"))
    parser.add_argument("--market", type=str, default=str(DATA_DIR / "seasonal_market.json"))
    parser.add_argument("--output", type=str, default=str(DATA_DIR / "shopping_ad_candidates.parquet"))
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"  축제 + 제철장터 통합 매칭")
    print(f"{'=' * 60}")

    # 1. 로드
    df_summary = pd.read_parquet(args.summary)
    print(f"\n  VOD 요약: {len(df_summary)}건")

    festival_matcher = FestivalMatcher(args.festivals)
    print(f"  축제: {festival_matcher.festival_count}건 / {len(festival_matcher.regions)}개 지역")

    seasonal_matcher = SeasonalMatcher(args.market)
    print(f"  제철장터: {seasonal_matcher.product_count}개 상품 / {seasonal_matcher.schedule_count}개 편성")

    vod_keywords = load_stt_keywords(PARQUET_DIR)
    print(f"  STT 음식 키워드: {len(vod_keywords)}개 VOD")

    # 2. 매칭
    candidates = []
    festival_count = 0
    market_count = 0

    for _, row in df_summary.iterrows():
        vod_id = row["vod_id"]
        ad_categories = json.loads(row["ad_categories"])
        ad_regions = json.loads(row["ad_regions"])
        primary_region = row["primary_region"]
        trigger_count = row["trigger_count"]

        # ── 관광지 → 축제 (primary_region만 사용) ──
        if "관광지" in ad_categories and primary_region:
            festivals = festival_matcher.match(primary_region)
            for f in festivals:
                candidates.append({
                    "vod_id": vod_id,
                    "ad_category": "관광지",
                    "ad_action_type": "local_gov_popup",
                    "region": f["region"],
                    "product_name": f["festival_name"],
                    "detail": f["period"],
                    "popup_title": f["popup_title"],
                    "popup_body": f["popup_body"],
                    "channel": None,
                    "trigger_count": trigger_count,
                })
                festival_count += 1

        # ── 음식 → 제철장터 실제 상품 ──
        if "음식" in ad_categories and vod_id in vod_keywords:
            keywords = vod_keywords[vod_id]
            matched = seasonal_matcher.match_keywords(keywords)
            for m in matched:
                candidates.append({
                    "vod_id": vod_id,
                    "ad_category": "음식",
                    "ad_action_type": "seasonal_market",
                    "region": primary_region,
                    "product_name": m["product_name"],
                    "detail": f"{m['broadcast_date']} {m['start_time']}~{m['end_time']}",
                    "popup_title": m["popup_title"],
                    "popup_body": m["popup_body"],
                    "channel": m["channel"],
                    "trigger_count": trigger_count,
                })
                market_count += 1

    # 3. 저장
    if candidates:
        df_out = pd.DataFrame(candidates)
        df_out.to_parquet(args.output, index=False)
        print(f"\n  저장: {args.output} ({len(df_out)}건)")
    else:
        print(f"\n  ❌ 매칭 결과 없음")
        return

    print(f"\n  📍 축제 매칭: {festival_count}건")
    print(f"  🛒 제철장터 매칭: {market_count}건")
    print(f"  합계: {len(candidates)}건")

    # 4. 결과 출력
    print(f"\n{'=' * 60}")
    print(f"  VOD별 광고 후보")
    print(f"{'=' * 60}")

    for vod_id in df_summary["vod_id"]:
        vod_ads = [c for c in candidates if c["vod_id"] == vod_id]
        if not vod_ads:
            print(f"\n  {vod_id}: 매칭 없음")
            continue

        print(f"\n  {vod_id} ({len(vod_ads)}건)")
        for ad in vod_ads:
            if ad["ad_action_type"] == "local_gov_popup":
                print(f"    📍 [{ad['region']}] {ad['product_name']} ({ad['detail']})")
            else:
                print(f"    🛒 [{ad['product_name']}] {ad['detail']} | 채널: {ad['channel']}")


if __name__ == "__main__":
    main()
