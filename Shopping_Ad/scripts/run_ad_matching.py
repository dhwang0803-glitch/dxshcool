"""
run_ad_matching.py — VOD 요약 → 축제 + 제철장터 통합 매칭

매칭 규칙 (2026-03-29 업데이트):
  - 음식 → 제철장터: 키워드 매칭 (지역 무관), YOLO 클로즈업 타이밍
  - 관광지 → 축제: 지역 일치 필수, 20% 이후 타이밍
  - 노출 우선순위: 축제 > 제철장터
  - OCR(자막) 여부 무관

실행:
    cd Shopping_Ad
    python scripts/run_ad_matching.py
"""
import os
import sys
import json
import re
import argparse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pandas as pd
import psycopg2

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from festival_matcher import FestivalMatcher
from seasonal_matcher import SeasonalMatcher

DATA_DIR = PROJECT_ROOT / "data"
PARQUET_DIR = PROJECT_ROOT.parent / "Object_Detection" / "data" / "parquet_output"
METADATA_PATH = PROJECT_ROOT.parent / "Object_Detection" / "data" / "batch_target" / "vod_metadata.json"


KNOWN_REGIONS = {
    "남원", "홍성", "아산", "양평", "군산", "무안", "양구",
    "제주", "강릉", "부산", "전주", "광주", "대전", "춘천",
    "영월", "보령", "여수", "통영", "경주", "속초", "하동",
    "삼척", "정선", "태백", "청주", "충주", "서귀포", "애월",
    "목포", "순천", "담양", "안동", "김해", "거제", "포항",
}

FOOD_KEYWORDS = {
    "추어탕", "김치", "막국수", "비빔밥", "한우", "갈비", "삼겹살",
    "회", "광어", "멍게", "소라", "해삼", "전복", "낙지", "꼬막",
    "짬뽕", "칼국수", "수제비", "떡볶이", "순대", "족발", "보쌈",
    "곱창", "육회", "불고기", "제육", "돈까스", "냉면", "쌈밥",
    "옥돔", "흑돼지", "귤", "감귤", "한라봉", "딸기", "복숭아",
    "곶감", "사과", "배", "포도", "수박", "참외", "마늘",
    "된장", "고추장", "젓갈", "굴비", "조기", "고등어", "갈치",
    "오징어", "문어", "새우", "게", "대게", "랍스터",
    "백반", "국밥", "설렁탕", "곰탕", "갈비탕", "삼계탕",
    "라면", "아이스크림", "떡", "한과", "약과",
}


def load_vod_smry():
    """DB에서 대상 VOD의 smry(줄거리)를 조회하여 {vod_id: smry} 반환"""
    if not METADATA_PATH.exists():
        print("  ⚠️ vod_metadata.json 없음 — smry 보강 스킵")
        return {}

    with open(METADATA_PATH, encoding="utf-8") as f:
        metadata = json.load(f)

    db_host = os.getenv("DB_HOST")
    if not db_host:
        print("  ⚠️ DB 환경변수 없음 — smry 보강 스킵")
        return {}

    conn = psycopg2.connect(
        host=db_host, port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
    )
    cur = conn.cursor()

    vod_smry = {}
    for item in metadata:
        asset_nm = item["asset_nm"]
        vod_id = item["file_id"]
        cur.execute(
            "SELECT smry FROM vod WHERE asset_nm ILIKE %s LIMIT 1",
            (f"%{asset_nm}%",),
        )
        row = cur.fetchone()
        if row and row[0]:
            vod_smry[vod_id] = row[0]

    conn.close()
    print(f"  smry 로드: {len(vod_smry)}건")
    return vod_smry


def extract_smry_regions(smry_text):
    """smry에서 지역명 추출"""
    found = []
    for region in KNOWN_REGIONS:
        if region in smry_text:
            found.append(region)
    return found


def extract_smry_foods(smry_text):
    """smry에서 음식 키워드 추출"""
    found = []
    for food in FOOD_KEYWORDS:
        if food in smry_text:
            found.append(food)
    return found


def score_match(match, primary_region, smry_regions, smry_foods):
    """제철장터 매칭 스코어링

    기본 점수 1 (STT 매칭)
    + 상품 지역 == smry 지역: +2
    + 상품 지역 == primary_region: +1
    + smry에 해당 음식 언급: +1
    """
    score = 1
    product_region = parse_product_region(match["product_name"])

    if product_region and product_region in smry_regions:
        score += 2
    if product_region and product_region == primary_region:
        score += 1
    if match["matched_keyword"] in smry_foods:
        score += 1

    return score


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


def _find_first_cluster(frames):
    """프레임 목록에서 첫 밀집 구간(30초 내 연속 2건+) 시작점 반환."""
    i = 0
    while i < len(frames):
        cluster = [frames[i]]
        j = i + 1
        while j < len(frames) and frames[j] - cluster[-1] <= 30:
            cluster.append(frames[j])
            j += 1
        if len(cluster) >= 2:
            return cluster[0]
        i = j if j > i + 1 else i + 1
    return None


def find_trigger_ts_food(parquet_dir, vod_id):
    """음식: YOLO 탐지 프레임 중 첫 밀집 구간 타이밍.

    min_pct 없음 (영상 처음부터 후보), OCR 여부 무관.
    음식 클로즈업 즉시 노출.

    Returns:
        (ts, signal_source) 튜플. 탐지 없으면 (None, None)
    """
    yolo_path = parquet_dir / "vod_detected_object.parquet"

    if yolo_path.exists():
        df = pd.read_parquet(str(yolo_path))
        vod_df = df[df["vod_id"] == vod_id]
        if len(vod_df) > 0 and "frame_ts" in vod_df.columns:
            frames = sorted(vod_df["frame_ts"].tolist())
            cluster_start = _find_first_cluster(frames)
            if cluster_start is not None:
                return cluster_start, "yolo"
            return frames[0], "yolo"

    # YOLO 없으면 STT fallback
    clip_path = parquet_dir / "vod_clip_concept.parquet"
    all_max_ts = 0
    for p in [yolo_path, clip_path]:
        if p.exists():
            df = pd.read_parquet(str(p))
            vod_df = df[df["vod_id"] == vod_id]
            if len(vod_df) > 0 and "frame_ts" in vod_df.columns:
                all_max_ts = max(all_max_ts, vod_df["frame_ts"].max())
    if all_max_ts > 0:
        return all_max_ts * 0.5, "stt"
    return None, None


def find_trigger_ts_tour(parquet_dir, vod_id, min_pct=0.2):
    """관광지: CLIP 탐지 프레임 중 20% 이후 첫 밀집 구간.

    OCR 여부 무관. 타이틀 시퀀스(앞 20%)만 회피.

    Returns:
        (ts, signal_source) 튜플. 탐지 없으면 (None, None)
    """
    clip_path = parquet_dir / "vod_clip_concept.parquet"

    if clip_path.exists():
        df = pd.read_parquet(str(clip_path))
        vod_df = df[
            (df["vod_id"] == vod_id) & (df["ad_category"] == "관광지")
        ]
        if len(vod_df) > 0 and "frame_ts" in vod_df.columns:
            frames = sorted(vod_df["frame_ts"].tolist())
            max_ts = max(frames)
            threshold = max_ts * min_pct
            late_frames = [ts for ts in frames if ts >= threshold]
            candidates = late_frames if late_frames else frames

            cluster_start = _find_first_cluster(candidates)
            if cluster_start is not None:
                return cluster_start, "clip"
            return candidates[0], "clip"

    # CLIP 없으면 STT fallback
    yolo_path = parquet_dir / "vod_detected_object.parquet"
    all_max_ts = 0
    for p in [yolo_path, clip_path]:
        if p.exists():
            df = pd.read_parquet(str(p))
            vod_df = df[df["vod_id"] == vod_id]
            if len(vod_df) > 0 and "frame_ts" in vod_df.columns:
                all_max_ts = max(all_max_ts, vod_df["frame_ts"].max())
    if all_max_ts > 0:
        return all_max_ts * min_pct, "stt"
    return None, None


def parse_product_region(product_name):
    """상품명에서 지역 파싱: '아산 포기김치' → '아산'"""
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
    print(f"  축제 + 제철장터 통합 매칭 (Top {args.top_n} + 카테고리별 타이밍)")
    print(f"{'=' * 60}")

    # 1. 로드
    df_summary = pd.read_parquet(args.summary)
    print(f"\n  VOD 요약: {len(df_summary)}건")

    # vod_id → full_asset_id 매핑
    mapping_path = DATA_DIR / "vod_id_mapping.json"
    if mapping_path.exists():
        with open(mapping_path, encoding="utf-8") as f:
            vod_id_map = json.load(f)
        print(f"  vod_id 매핑: {len(vod_id_map)}건")
    else:
        vod_id_map = {}
        print("  ⚠ vod_id_mapping.json 없음 — file_id 그대로 사용")

    festival_matcher = FestivalMatcher(args.festivals)
    print(f"  축제: {festival_matcher.festival_count}건 / {len(festival_matcher.regions)}개 지역")

    seasonal_matcher = SeasonalMatcher(args.market)
    print(f"  제철장터: {seasonal_matcher.product_count}개 상품 / {seasonal_matcher.schedule_count}개 편성")

    vod_keywords = load_stt_top_keywords(PARQUET_DIR, top_n=args.top_n)
    print(f"  STT Top {args.top_n} 키워드: {len(vod_keywords)}개 VOD")

    # smry 로드
    vod_smry = load_vod_smry()

    # 2. 매칭
    candidates = []
    festival_count = 0
    market_count = 0

    for _, row in df_summary.iterrows():
        vod_id = row["vod_id"]
        ad_categories = json.loads(row["ad_categories"])
        primary_region = row["primary_region"]
        trigger_count = row["trigger_count"]

        # ── 관광지 → 축제 (우선 노출, VOD당 1건만) ──
        festival_count_this_vod = 0
        if "관광지" in ad_categories and primary_region:
            trigger_ts, sig_src = find_trigger_ts_tour(PARQUET_DIR, vod_id)
            festivals = festival_matcher.match(primary_region)
            for f in festivals[:1]:  # VOD당 축제 1건만
                gif_name = f"popup_{f['region']}_{f['festival_name']}.gif"
                gif_path = DATA_DIR / "ad_gifs" / gif_name
                ad_image_url = f"ad_gifs/{gif_name}" if gif_path.exists() else None
                candidates.append({
                    "vod_id": vod_id,
                    "vod_id_fk": vod_id_map.get(vod_id, vod_id),
                    "ad_category": "관광지",
                    "ad_action_type": "local_gov_popup",
                    "signal_source": sig_src or "stt",
                    "score": round(min(trigger_count / 110, 1.0), 4),
                    "ad_hints": json.dumps([f["region"], f["festival_name"]], ensure_ascii=False),
                    "ad_image_url": ad_image_url,
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

        # ── 음식 → 제철장터 (축제 매칭 없을 때만, smry 보강 + 스코어링) ──
        if festival_count_this_vod > 0:
            pass  # 축제 있으면 제철장터 스킵
        elif "음식" in ad_categories:
            trigger_ts, sig_src = find_trigger_ts_food(PARQUET_DIR, vod_id)
            # STT Top N 키워드
            top_keywords = vod_keywords.get(vod_id, [])

            # smry 보강: smry에서 음식 키워드 추출 → STT에 없는 것만 추가
            smry_text = vod_smry.get(vod_id, "")
            smry_regions = extract_smry_regions(smry_text) if smry_text else []
            smry_foods = extract_smry_foods(smry_text) if smry_text else []

            all_keywords = list(top_keywords)
            for food in smry_foods:
                if food not in all_keywords:
                    all_keywords.append(food)

            if not all_keywords:
                continue

            # 1위 키워드가 제철장터에 없으면 스킵
            # (동치미 → 매칭 없음 → "김치"로 "아산 포기김치" 잘못 매칭 방지)
            if not seasonal_matcher.match(all_keywords[0]):
                continue

            matched = seasonal_matcher.match_keywords(all_keywords)

            if not matched:
                continue

            # 스코어링 → 최고 점수 1건 선택
            scored = []
            for m in matched:
                s = score_match(m, primary_region, smry_regions, smry_foods)
                scored.append((s, m))
            scored.sort(key=lambda x: -x[0])

            best_score, best = scored[0]
            candidates.append({
                "vod_id": vod_id,
                "vod_id_fk": vod_id_map.get(vod_id, vod_id),
                "ad_category": "음식",
                "ad_action_type": "seasonal_market",
                "signal_source": sig_src or "stt",
                "score": round(min(trigger_count / 110, 1.0), 4),
                "ad_hints": json.dumps([best["product_name"], best.get("matched_keyword", "")], ensure_ascii=False),
                "ad_image_url": None,
                "region": primary_region,
                "product_name": best["product_name"],
                "detail": f"{best['broadcast_date']} {best['start_time']}~{best['end_time']}",
                "popup_text_live": best["popup_text_live"],
                "popup_text_scheduled": best["popup_text_scheduled"],
                "channel": best["channel"],
                "ts_start": trigger_ts,
                "ts_end": (trigger_ts + 10) if trigger_ts else None,
                "trigger_count": trigger_count,
                "priority": 2,
                "match_score": best_score,
                "matched_keyword": best["matched_keyword"],
                "smry_keywords": json.dumps(smry_foods, ensure_ascii=False),
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
                score = ad.get('match_score', '-')
                kw = ad.get('matched_keyword', '')
                print(f"    🛒 [{ad['product_name']}] {ad['detail']} | 채널: {ad['channel']} | score={score} kw={kw}{ts}")


if __name__ == "__main__":
    main()
