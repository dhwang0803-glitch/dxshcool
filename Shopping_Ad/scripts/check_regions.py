"""VOD별 primary_region 확인"""
import pandas as pd, json
df = pd.read_parquet("data/vod_ad_summary.parquet")
for _, row in df.iterrows():
    regions = json.loads(row["ad_regions"])
    print(f"{row['vod_id']}: primary={row['primary_region']}, regions={regions}")
