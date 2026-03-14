"""파일럿 parquet 카테고리별 인식률 분석"""
import pandas as pd
from pathlib import Path

df = pd.read_parquet(Path(__file__).parent.parent / "data" / "vod_detected_object.parquet")

food  = ["apple","banana","orange","pizza","cake","donut","sandwich","hot dog","carrot","broccoli","cup","bowl","bottle"]
cloth = ["person","handbag","backpack","tie","suitcase"]
furn  = ["couch","chair","tv","laptop","cell phone","refrigerator","dining table","bed","clock","vase"]

n = df.vod_id.nunique()
print(f"전체 VOD: {n}건")
print(f"음식 탐지: {df[df.label.isin(food)].vod_id.nunique()}건 ({df[df.label.isin(food)].vod_id.nunique()/n*100:.0f}%)")
print(f"옷/사람:   {df[df.label.isin(cloth)].vod_id.nunique()}건 ({df[df.label.isin(cloth)].vod_id.nunique()/n*100:.0f}%)")
print(f"가구/가전: {df[df.label.isin(furn)].vod_id.nunique()}건 ({df[df.label.isin(furn)].vod_id.nunique()/n*100:.0f}%)")
print("\n--- 음식 라벨 ---")
print(df[df.label.isin(food)].label.value_counts().to_string())
print("\n--- 옷/사람 라벨 ---")
print(df[df.label.isin(cloth)].label.value_counts().to_string())
print("\n--- 가구/가전 라벨 ---")
print(df[df.label.isin(furn)].label.value_counts().to_string())
