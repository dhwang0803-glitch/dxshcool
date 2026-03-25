"""제철장터 매칭 VOD에서 50% 이후 + OCR 없는 음식 프레임 찾기"""
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
PARQUET_DIR = PROJECT_ROOT.parent / "Object_Detection" / "data" / "parquet_output"

vods = ["food_altoran_418", "food_altoran_490", "travel_chonnom_03", "travel_dongwon_12"]

clip = pd.read_parquet(str(PARQUET_DIR / "vod_clip_concept.parquet"))
ocr = pd.read_parquet(str(PARQUET_DIR / "vod_ocr_concept.parquet"))
results = pd.read_parquet(str(PROJECT_ROOT / "data" / "shopping_ad_candidates.parquet"))
market = results[results["ad_action_type"] == "seasonal_market"]

print("=== 매칭 결과 ===")
for _, row in market.iterrows():
    print(f"  {row['vod_id']} | {row['product_name']} | score={row['match_score']}")
    print(f"    예정: {row['popup_text_scheduled'][:60]}...")
    print(f"    ts_start: {row['ts_start']:.0f}s")
    print()

print("=== 클린 음식 프레임 (50% 이후 + OCR 없음) ===")
for v in vods:
    vc = clip[(clip["vod_id"] == v) & (clip["ad_category"] == "음식")]
    max_ts = clip[clip["vod_id"] == v]["frame_ts"].max()
    half = max_ts * 0.5
    vc2 = vc[vc["frame_ts"] >= half]
    vo = set(ocr[ocr["vod_id"] == v]["frame_ts"].round(0).astype(int).tolist())
    clean = vc2[~vc2["frame_ts"].round(0).astype(int).isin(vo)]

    if len(clean) > 0:
        row = clean.iloc[0]
        print(f"  {v} | ts={row['frame_ts']:.1f}s | {row['concept']}")
    else:
        print(f"  {v} | 클린 음식 프레임 없음")
