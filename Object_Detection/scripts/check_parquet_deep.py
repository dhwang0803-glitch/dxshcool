"""parquet 심층 품질 체크 — YOLO/CLIP/STT 상세 검증"""
import pandas as pd
from pathlib import Path

PARQUET_DIR = Path(__file__).parent.parent / "data" / "parquet_output"

EXPECTED_VODS = [
    "travel_dongwon_06", "travel_dongwon_11", "travel_dongwon_12",
    "travel_dongwon_15", "travel_dongwon_16",
    "travel_chonnom_01", "travel_chonnom_03", "travel_chonnom_05",
    "travel_chonnom_07", "travel_chonnom_09",
    "food_altoran_418", "food_altoran_440", "food_altoran_490", "food_altoran_496",
    "food_local_dakgalbi", "food_local_keyjo", "food_local_memill",
    "food_local_samchi", "food_local_sugyuk",
]

issues = []

# ── YOLO ──
print("=" * 60)
print("  YOLO 심층 체크")
print("=" * 60)
df = pd.read_parquet(str(PARQUET_DIR / "vod_detected_object.parquet"))
print(f"  행: {len(df)}, 컬럼: {list(df.columns)}")

# NULL
for col in df.columns:
    n = df[col].isna().sum()
    if n > 0:
        issues.append(f"YOLO {col}: {n}건 NULL")
        print(f"  ❌ {col}: {n}건 NULL")

# label 값
labels = df["label"].unique()
print(f"  label 종류: {list(labels)}")
if "food_detected" not in labels:
    issues.append("YOLO: food_detected 없음")

# confidence 범위
print(f"  confidence: {df['confidence'].min():.3f} ~ {df['confidence'].max():.3f}")
bad_conf = df[(df["confidence"] < 0) | (df["confidence"] > 1)]
if len(bad_conf) > 0:
    issues.append(f"YOLO confidence 범위 벗어남: {len(bad_conf)}건")

# bbox 형식
sample_bbox = df["bbox"].iloc[0] if len(df) > 0 else None
print(f"  bbox 샘플: {sample_bbox}")
if sample_bbox is not None:
    if isinstance(sample_bbox, list) and len(sample_bbox) == 4:
        print(f"  bbox 형식: ✅ [x1,y1,x2,y2]")
    else:
        issues.append(f"YOLO bbox 형식 이상: {type(sample_bbox)} len={len(sample_bbox) if hasattr(sample_bbox,'__len__') else '?'}")

# VOD 누락
missing = [v for v in EXPECTED_VODS if v not in df["vod_id"].unique()]
# YOLO는 음식 없는 영상이면 0건일 수 있음
if missing:
    print(f"  YOLO 없는 VOD: {missing} (음식 없으면 정상)")

print()

# ── CLIP ──
print("=" * 60)
print("  CLIP 심층 체크")
print("=" * 60)
df = pd.read_parquet(str(PARQUET_DIR / "vod_clip_concept.parquet"))
print(f"  행: {len(df)}, 컬럼: {list(df.columns)}")

for col in df.columns:
    n = df[col].isna().sum()
    if col == "context_reason":
        continue  # NULL 허용
    if n > 0:
        issues.append(f"CLIP {col}: {n}건 NULL")
        print(f"  ❌ {col}: {n}건 NULL")

# ad_category 값
cats = df["ad_category"].unique()
print(f"  ad_category 종류: {list(cats)}")

# clip_score 범위
print(f"  clip_score: {df['clip_score'].min():.3f} ~ {df['clip_score'].max():.3f}")

# context_valid 분포
print(f"  context_valid: True={df['context_valid'].sum()}, False={(~df['context_valid']).sum()}")

# context_reason NULL 비율
cr_null = df["context_reason"].isna().sum()
print(f"  context_reason: NULL={cr_null}, 값있음={len(df)-cr_null}")

# VOD 누락
missing = [v for v in EXPECTED_VODS if v not in df["vod_id"].unique()]
if missing:
    print(f"  ❌ CLIP 없는 VOD: {missing}")
    issues.append(f"CLIP 누락 VOD: {missing}")
else:
    print(f"  ✅ 19개 VOD 전부 있음")

print()

# ── STT ──
print("=" * 60)
print("  STT 심층 체크")
print("=" * 60)
df = pd.read_parquet(str(PARQUET_DIR / "vod_stt_concept.parquet"))
print(f"  행: {len(df)}, 컬럼: {list(df.columns)}")

for col in df.columns:
    n = df[col].isna().sum()
    if col in ("transcript", "ad_hints"):
        continue  # NULL 허용
    if n > 0:
        issues.append(f"STT {col}: {n}건 NULL")
        print(f"  ❌ {col}: {n}건 NULL")

# ad_category 값
cats = df["ad_category"].unique()
print(f"  ad_category 종류: {list(cats)}")

# 타임스탬프 일관성
bad_ts = df[df["end_ts"] < df["start_ts"]]
if len(bad_ts) > 0:
    issues.append(f"STT end_ts < start_ts: {len(bad_ts)}건")
    print(f"  ❌ end_ts < start_ts: {len(bad_ts)}건")
else:
    print(f"  ✅ end_ts >= start_ts 전부 OK")

# keyword 빈값
empty_kw = df[df["keyword"].str.strip() == ""]
if len(empty_kw) > 0:
    issues.append(f"STT keyword 빈값: {len(empty_kw)}건")
else:
    print(f"  ✅ keyword 빈값 없음")

# 상위 키워드
print(f"  상위 10 키워드:")
for kw, cnt in df["keyword"].value_counts().head(10).items():
    print(f"    {kw}: {cnt}건")

# VOD 누락
missing = [v for v in EXPECTED_VODS if v not in df["vod_id"].unique()]
if missing:
    print(f"  ⚠️ STT 없는 VOD: {missing} (대화 없으면 정상)")

print()

# ── 최종 ──
print("=" * 60)
print("  최종 결과")
print("=" * 60)
if issues:
    print(f"  ❌ 이슈 {len(issues)}건:")
    for i in issues:
        print(f"    - {i}")
else:
    print(f"  ✅ YOLO/CLIP/STT 전부 이상 없음")
