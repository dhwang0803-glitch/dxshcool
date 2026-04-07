"""왜 제주가 primary_region인지 상세 확인"""
import pandas as pd, json
from pathlib import Path

PARQUET_DIR = Path(__file__).parent.parent.parent / "Object_Detection" / "data" / "parquet_output"

# VOD 요약
df_sum = pd.read_parquet("data/vod_ad_summary.parquet")

# STT 원본
df_stt = pd.read_parquet(str(PARQUET_DIR / "vod_stt_concept.parquet"))

# OCR 원본
df_ocr = pd.read_parquet(str(PARQUET_DIR / "vod_ocr_concept.parquet"))

for vod in ["food_local_sugyuk", "travel_dongwon_15"]:
    row = df_sum[df_sum["vod_id"] == vod].iloc[0]
    print(f"\n{'='*60}")
    print(f"  {vod}")
    print(f"  primary_region: {row['primary_region']}")
    print(f"  ad_regions: {json.loads(row['ad_regions'])}")
    print(f"{'='*60}")

    # STT 관광지 키워드 빈도
    stt_tour = df_stt[(df_stt["vod_id"] == vod) & (df_stt["ad_category"] == "관광지")]
    if len(stt_tour) > 0:
        print(f"\n  STT 관광지 키워드:")
        for kw, cnt in stt_tour["keyword"].value_counts().items():
            print(f"    {kw}: {cnt}건")
    else:
        print(f"\n  STT 관광지: 0건")

    # OCR region_hint 빈도
    ocr_vod = df_ocr[(df_ocr["vod_id"] == vod) & (df_ocr["region_hint"].notna())]
    if len(ocr_vod) > 0:
        print(f"\n  OCR region_hint:")
        for kw, cnt in ocr_vod["region_hint"].value_counts().items():
            print(f"    {kw}: {cnt}건")
    else:
        print(f"\n  OCR region_hint: 0건")
