"""기존 parquet 컬럼을 DB 스키마에 맞게 수정"""
import pandas as pd
from pathlib import Path

PARQUET_DIR = Path(__file__).parent.parent / "data" / "parquet_output"

# 1. YOLO — context 컬럼 제거
yolo_path = PARQUET_DIR / "vod_detected_object.parquet"
if yolo_path.exists():
    df = pd.read_parquet(str(yolo_path))
    before = list(df.columns)
    df = df[["vod_id", "frame_ts", "label", "confidence", "bbox"]]
    df.to_parquet(str(yolo_path), index=False)
    print(f"✅ YOLO: {before} → {list(df.columns)} ({len(df)}행)")

# 2. CLIP — context_valid, context_reason 추가
clip_path = PARQUET_DIR / "vod_clip_concept.parquet"
if clip_path.exists():
    df = pd.read_parquet(str(clip_path))
    before = list(df.columns)
    if "context_valid" not in df.columns:
        df["context_valid"] = True
    if "context_reason" not in df.columns:
        df["context_reason"] = None
    df = df[["vod_id", "frame_ts", "concept", "clip_score", "ad_category", "context_valid", "context_reason"]]
    df.to_parquet(str(clip_path), index=False)
    print(f"✅ CLIP: {before} → {list(df.columns)} ({len(df)}행)")

# 3. STT — context_valid, context_reason 제거
stt_path = PARQUET_DIR / "vod_stt_concept.parquet"
if stt_path.exists():
    df = pd.read_parquet(str(stt_path))
    before = list(df.columns)
    keep = ["vod_id", "start_ts", "end_ts", "transcript", "keyword", "ad_category", "ad_hints"]
    df = df[[c for c in keep if c in df.columns]]
    df.to_parquet(str(stt_path), index=False)
    print(f"✅ STT: {before} → {list(df.columns)} ({len(df)}행)")

# 4. OCR — DB 없으므로 그대로
print(f"ℹ️ OCR: DB 테이블 없음, 변경 없음")

print(f"\n완료. 다시 check_parquet_vs_db.py 실행하세요.")
