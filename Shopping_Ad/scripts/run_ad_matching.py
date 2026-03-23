"""
run_ad_matching.py — VOD 요약 → 축제 + 제철장터 통합 매칭

매칭 규칙 (2026-03-23 확정):
  - 제철장터: Top 3 키워드만 매칭 (곁들이 제거)
  - 상품명 지역 파싱 → VOD 지역과 우선 매칭
  - 노출 우선순위: 축제 > 제철장터
  - 타이밍: 영상 50% 이상 + OCR 없는 클린 화면

실행:
    cd Shopping_Ad
    python scripts/run_ad_matching.py
"""
import sys
import json
import re
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


def load_stt_top_keywords(parquet_dir, top_n=3):
    """STT parquet에서 VOD별 음식 Top N 키워드만 수집"""
    stt_path = parquet_dir / "vod_stt_concept.parquet"
    if not stt_path.exists():
        return {}

    df = pd.read_parquet(str(stt_path))
    df_food = df[df["ad_category"] == "음식"]

    vod_keywords = {}
    for vod_id, group in df_food.groupby("vod_id"):
        # 빈도 상위 N개만
        top = list(group["keyword"].value_counts().head(top_n).index)
        vod_keywords[vod_id] = top
    return vod_keywords


def find_clean_trigger_ts(parquet_dir, vod_id, min_pct=0.5):
    """영상 50% 이후 + OCR 없는 클린 구간의 frame_ts 찾기"""
    # YOLO에서 영상 길이 추정
    yolo_path = parquet_dir / "vod_detected_object.parquet"
    clip_path = parquet_dir / "vod_clip_concept.parquet"
    ocr_path = parquet_dir / "vod_ocr_concept.parquet"

    max_ts = 0
    for p in [yolo_path, clip_path]:
        if p.exists():
            df = pd.read_parquet(str(p))
            vod_df = df[df["vod_id"] == vod_id]
            if len(vod_df) > 0 and "frame_ts" in vod_df.columns:
                max_ts = max(max_ts, vod_df["frame_ts"].max())

    if max_ts == 0:
        return None

    half_ts = max_ts * min_pct

    # OCR이 있는 타임스탬프 수집
    ocr_timestamps = set()
    if ocr_path.exists():
        df_ocr = pd.read_parquet(str(ocr_path))
        vod_ocr = df_ocr[df_ocr["vod_id"] == vod_id]
        if len(vod_ocr) > 0:
            ocr_timestamps = set(vod_ocr["frame_ts"].round(0).astype(int).tolist())

    # 50% 이후 + OCR 없는 10초 구간 찾기
    for t_start in range(int(half_ts), int(max_ts), 10):
        t_end = t_start + 10
        # 이 구간에 OCR이 없는지 확인
        has_ocr = any(t_start <= ts < t_end for ts in ocr_timestamps)
        if not has_ocr:
            return float(t_start)

    # 클린 구간 못 찾으면 50% 지점 반환
    return half_ts


def parse_product_region(product_name):
    """상품명에서 지역 파싱: '아산 포기김치' → '아산'"""
    # 공백으로 분리해서 첫 단어가 지역명인지 확인
    KNOWN_REGIONS = {
        "남원", "홍성", "아산", "양평", "군산", "무안", "양구",
        "제주", "강릉", "부산", "전주", "광주", "대전", "춘천",
        "영월", "보령", "여수", "통영", "경주", "속초", "하동",
    }
    parts = product_name.split()
    if parts and parts[0] in KNOWN_REGIONS:
        return parts[0]
    # 붙어있는 경우: "홍성마늘등심" → "홍성"
    for region in KNOWN_REGIONS:
        if product_name.startswith(region):
            return region
    return None


def main():
    parser = argparse.ArgumentParser(description="축제 + 제철장터 통합 매칭")
    parser.add_argument("--summary", type=str, default=str(DATA_DIR / "vod_ad_summary.parquet"))
    parser.add_argument("--festivals", type=str, default=str(DATA_DIR / "region_festivals.yaml"))
    parser.add_argument("--market", type=str, default=str(DATA_DIR / "seasonal_market.json"))
    parser.add_argument("--output", type=str, default=str(DATA_DIR / "shopping_ad_candidates.parquet"))
    parser.add_argument("--top-n", type=int, default=3, help="음식 키워드 상위 N개만 매칭")
    args = parser.parse_args()

    print(f"{'=' * 60}")
    print(f"  축제 + 제철장터 통합 매칭 (Top {args.top_n} + 지역 파싱 + 50% 타이밍)")
    print(f"{'=' * 60}")

    # 1. 로드
    df_summary = pd.read_parquet(args.summary)
    print(f"\n  VOD 요약: {len(df_summary)}건")

    festival_matcher = FestivalMatcher(args.festivals)
    print(f"  축제: {festival_matcher.festival_count}건 / {len(festival_matcher.regions)}개 지역")

    seasonal_matcher = SeasonalMatcher(args.market)
    print(f"  제철장터: {seasonal_matcher.product_count}개 상품 / {seasonal_matcher.schedule_count}개 편성")

    vod_keywords = load_stt_top_keywords(PARQUET_DIR, top_n=args.top_n)
    print(f"  STT Top {args.top_n} 키워드: {len(vod_keywords)}개 VOD")

    # 2. 매칭
    candidates = []
    festival_count = 0
    market_count = 0

    for _, row in df_summary.iterrows():
        vod_id = row["vod_id"]
        ad_categories = json.loads(row["ad_categories"])
        primary_region = row["primary_region"]
        trigger_count = row["trigger_count"]

        # 50% + 클린 화면 타이밍
        trigger_ts = find_clean_trigger_ts(PARQUET_DIR, vod_id)

        # ── 관광지 → 축제 (우선 노출, VOD당 1건만) ──
        festival_count_this_vod = 0
        if "관광지" in ad_categories and primary_region:
            festivals = festival_matcher.match(primary_region)
            for f in festivals[:1]:  # VOD당 축제 1건만
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
                    "ts_start": trigger_ts,
                    "ts_end": (trigger_ts + 10) if trigger_ts else None,
                    "trigger_count": trigger_count,
                    "priority": 1,  # 축제 우선
                })
                festival_count += 1
                festival_count_this_vod += 1

        # ── 음식 → 제철장터 (축제 매칭 없을 때만, Top N 키워드, 지역 우선) ──
        if festival_count_this_vod > 0:
            pass  # 축제 있으면 제철장터 스킵
        elif "음식" in ad_categories and vod_id in vod_keywords:
            top_keywords = vod_keywords[vod_id]
            matched = seasonal_matcher.match_keywords(top_keywords)

            # 지역 우선 정렬: VOD 지역과 같은 상품 우선
            if primary_region and matched:
                def region_priority(m):
                    product_region = parse_product_region(m["product_name"])
                    if product_region and product_region == primary_region:
                        return 0  # 같은 지역 우선
                    return 1
                matched.sort(key=region_priority)

            for m in matched[:1]:  # VOD당 제철장터 1건만
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
                    "ts_start": trigger_ts,
                    "ts_end": (trigger_ts + 10) if trigger_ts else None,
                    "trigger_count": trigger_count,
                    "priority": 2,  # 제철장터는 축제 다음
                })
                market_count += 1

    # 3. 저장
    if candidates:
        df_out = pd.DataFrame(candidates)
        df_out = df_out.sort_values(["vod_id", "priority"])
        df_out.to_parquet(args.output, index=False)
        print(f"\n  저장: {args.output} ({len(df_out)}건)")
    else:
        print(f"\n  ❌ 매칭 결과 없음")
        return

    print(f"\n  📍 축제 매칭: {festival_count}건")
    print(f"  🛒 제철장터 매칭: {market_count}건 (Top {args.top_n} 키워드만)")
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
            ts = f" @{int(ad['ts_start'])}초" if ad['ts_start'] else ""
            if ad["ad_action_type"] == "local_gov_popup":
                print(f"    📍 [{ad['region']}] {ad['product_name']} ({ad['detail']}){ts}")
            else:
                print(f"    🛒 [{ad['product_name']}] {ad['detail']} | 채널: {ad['channel']}{ts}")


if __name__ == "__main__":
    main()
