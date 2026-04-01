"""특정 키워드가 어떤 장면에서 잡혔는지 확인"""
import pandas as pd
from pathlib import Path

PARQUET_DIR = Path(__file__).parent.parent.parent / "Object_Detection" / "data" / "parquet_output"

df = pd.read_parquet(str(PARQUET_DIR / "vod_stt_concept.parquet"))

# 동원아 여행가자 + 김치 키워드
print("=== 동원아 여행가자 — '김치' 키워드 장면 ===")
for vod in sorted(df["vod_id"].unique()):
    if "dongwon" not in vod:
        continue
    matches = df[(df["vod_id"] == vod) & (df["keyword"] == "김치")]
    if len(matches) > 0:
        print(f"\n  {vod}:")
        for _, row in matches.iterrows():
            m = int(row["start_ts"] // 60)
            s = int(row["start_ts"] % 60)
            print(f"    [{m:02d}:{s:02d}] \"{row['transcript'][:60]}\"")

# 전체 VOD에서 아산 포기김치와 매칭된 키워드 확인
print("\n\n=== '김치' 키워드가 잡힌 모든 VOD ===")
kimchi = df[df["keyword"] == "김치"]
for vod in sorted(kimchi["vod_id"].unique()):
    matches = kimchi[kimchi["vod_id"] == vod]
    print(f"\n  {vod} ({len(matches)}건):")
    for _, row in matches.iterrows():
        m = int(row["start_ts"] // 60)
        s = int(row["start_ts"] % 60)
        print(f"    [{m:02d}:{s:02d}] \"{row['transcript'][:60]}\"")
