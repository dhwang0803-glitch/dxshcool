"""parquet 데이터 품질 체크 — NULL, 누락, 이상값 검사"""
import pandas as pd
from pathlib import Path

PARQUET_DIR = Path(__file__).parent.parent / "data" / "parquet_output"

files = [
    ("vod_detected_object.parquet", "YOLO"),
    ("vod_clip_concept.parquet", "CLIP"),
    ("vod_stt_concept.parquet", "STT"),
    ("vod_ocr_concept.parquet", "OCR"),
]

for fname, label in files:
    path = PARQUET_DIR / fname
    if not path.exists():
        print(f"\n❌ {label}: 파일 없음")
        continue

    df = pd.read_parquet(str(path))
    print(f"\n{'=' * 60}")
    print(f"  {label} ({fname}) — {len(df)}행, {len(df.columns)}컬럼")
    print(f"{'=' * 60}")

    # 1. NULL 체크
    print(f"\n  [NULL 체크]")
    for col in df.columns:
        null_count = df[col].isna().sum()
        null_pct = null_count / len(df) * 100 if len(df) > 0 else 0
        if null_count > 0:
            print(f"    ⚠️ {col}: {null_count}건 NULL ({null_pct:.1f}%)")
        else:
            print(f"    ✅ {col}: NULL 없음")

    # 2. VOD별 건수
    print(f"\n  [VOD별 건수]")
    vod_counts = df["vod_id"].value_counts()
    for vod_id, cnt in vod_counts.items():
        print(f"    {vod_id}: {cnt}건")

    # 3. 19개 영상 누락 체크
    expected_vods = [
        "travel_dongwon_06", "travel_dongwon_11", "travel_dongwon_12",
        "travel_dongwon_15", "travel_dongwon_16",
        "travel_chonnom_01", "travel_chonnom_03", "travel_chonnom_05",
        "travel_chonnom_07", "travel_chonnom_09",
        "food_altoran_418", "food_altoran_440", "food_altoran_490", "food_altoran_496",
        "food_local_dakgalbi", "food_local_keyjo", "food_local_memill",
        "food_local_samchi", "food_local_sugyuk",
    ]
    present = set(df["vod_id"].unique())
    missing = [v for v in expected_vods if v not in present]
    if missing:
        print(f"\n  ❌ 누락된 VOD: {missing}")
    else:
        print(f"\n  ✅ 19개 VOD 전부 있음")

    # 4. 값 범위 체크
    print(f"\n  [값 범위]")
    if "confidence" in df.columns:
        print(f"    confidence: {df['confidence'].min():.3f} ~ {df['confidence'].max():.3f}")
    if "clip_score" in df.columns:
        print(f"    clip_score: {df['clip_score'].min():.3f} ~ {df['clip_score'].max():.3f}")
    if "frame_ts" in df.columns:
        print(f"    frame_ts: {df['frame_ts'].min():.1f} ~ {df['frame_ts'].max():.1f}")
    if "start_ts" in df.columns:
        print(f"    start_ts: {df['start_ts'].min():.1f} ~ {df['start_ts'].max():.1f}")
    if "context_valid" in df.columns:
        print(f"    context_valid: True={df['context_valid'].sum()}, False={(~df['context_valid']).sum()}")
