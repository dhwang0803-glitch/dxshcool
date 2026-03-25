"""
run_ad_matching.py — VOD 요약 → 축제 + 제철장터 통합 매칭

매칭 규칙 (2026-03-24 업데이트):
  - 제철장터: Top 3 키워드 + smry 보강 키워드 매칭
  - 스코어링: 지역 일치 + smry 언급 가산 → 최고 점수 1건
  - 노출 우선순위: 축제 > 제철장터
  - 타이밍: 영상 50% 이상 + OCR 없는 클린 화면

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

        # ── 음식 → 제철장터 (축제 매칭 없을 때만, smry 보강 + 스코어링) ──
        if festival_count_this_vod > 0:
            pass  # 축제 있으면 제철장터 스킵
        elif "음식" in ad_categories:
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
                "ad_category": "음식",
                "ad_action_type": "seasonal_market",
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
