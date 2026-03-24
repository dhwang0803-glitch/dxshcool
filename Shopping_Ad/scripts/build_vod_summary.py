"""
build_vod_summary.py — Object_Detection parquet 4종 → VOD 요약 집계

VOD별 ad_category, region, trigger_count, 상위 키워드를 집계하여
vod_ad_summary.parquet을 생성한다. Shopping_Ad 매칭의 입력.

실행:
    cd Shopping_Ad
    python scripts/build_vod_summary.py
    python scripts/build_vod_summary.py --parquet-dir ../Object_Detection/data/parquet_output
"""
import sys
import argparse
import json
from pathlib import Path
from collections import Counter

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_PARQUET_DIR = PROJECT_ROOT.parent / "Object_Detection" / "data" / "parquet_output"
OUTPUT_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def load_parquet(parquet_dir, name):
    path = parquet_dir / name
    if path.exists():
        return pd.read_parquet(str(path))
    print(f"  ⚠️ {name} 없음")
    return pd.DataFrame()


def build_summary(parquet_dir):
    """parquet 4종 → VOD별 요약 dict 리스트"""
    df_yolo = load_parquet(parquet_dir, "vod_detected_object.parquet")
    df_clip = load_parquet(parquet_dir, "vod_clip_concept.parquet")
    df_stt = load_parquet(parquet_dir, "vod_stt_concept.parquet")
    df_ocr = load_parquet(parquet_dir, "vod_ocr_concept.parquet")

    # 모든 VOD ID 수집
    all_vods = set()
    for df in [df_yolo, df_clip, df_stt, df_ocr]:
        if "vod_id" in df.columns:
            all_vods.update(df["vod_id"].unique())

    summaries = []
    for vod_id in sorted(all_vods):
        # 각 신호별 필터
        yolo = df_yolo[df_yolo["vod_id"] == vod_id] if len(df_yolo) > 0 else pd.DataFrame()
        clip = df_clip[df_clip["vod_id"] == vod_id] if len(df_clip) > 0 else pd.DataFrame()
        stt = df_stt[df_stt["vod_id"] == vod_id] if len(df_stt) > 0 else pd.DataFrame()
        ocr = df_ocr[df_ocr["vod_id"] == vod_id] if len(df_ocr) > 0 else pd.DataFrame()

        # ad_category 집계 (CLIP + STT + OCR)
        categories = Counter()
        if "ad_category" in clip.columns:
            categories.update(clip["ad_category"].dropna().tolist())
        if "ad_category" in stt.columns:
            categories.update(stt["ad_category"].dropna().tolist())
        if "ad_category" in ocr.columns:
            categories.update(ocr["ad_category"].dropna().tolist())

        ad_categories = list(set(categories.keys()))

        # region 집계 (STT + OCR 관광지 키워드)
        regions = Counter()
        if "keyword" in stt.columns and "ad_category" in stt.columns:
            tour_stt = stt[stt["ad_category"] == "관광지"]
            regions.update(tour_stt["keyword"].tolist())
        if "region_hint" in ocr.columns:
            regions.update(ocr["region_hint"].dropna().tolist())

        ad_regions = [r for r, _ in regions.most_common(10)]

        # primary_region: 도시/지역명 우선, 명소(경기전, 태종대 등) 후순위
        # 명소는 보통 3글자 이상 + 산/사/궁/대교/시장 등 포함
        LANDMARK_SUFFIXES = ("산", "사", "궁", "대교", "시장", "오일장", "해변", "해수욕장",
                             "마을", "성", "봉", "폭포", "길", "공원")
        KNOWN_LANDMARKS = {"경기전", "객사", "태종대", "광안대교", "상당산성",
                           "정선아리랑시장", "정선오일장", "한옥마을", "순천만"}

        def is_landmark(name):
            if name in KNOWN_LANDMARKS:
                return True
            for suffix in LANDMARK_SUFFIXES:
                if name.endswith(suffix):
                    return True
            return False

        # 도시 우선 정렬: 명소가 아닌 것 먼저
        cities = [r for r in ad_regions if not is_landmark(r)]
        landmarks = [r for r in ad_regions if is_landmark(r)]
        ad_regions_sorted = cities + landmarks
        ad_regions = ad_regions_sorted[:5]
        primary_region = ad_regions[0] if ad_regions else None

        # 상위 키워드 (STT 기준)
        top_keywords = []
        if "keyword" in stt.columns:
            top_keywords = [kw for kw, _ in stt["keyword"].value_counts().head(5).items()]

        # ad_hints 집계 (STT)
        ad_hints_list = []
        if "ad_hints" in stt.columns:
            ad_hints_list = list(stt["ad_hints"].dropna().unique()[:5])

        # 신호 건수
        yolo_count = len(yolo)
        clip_count = len(clip)
        stt_count = len(stt)
        ocr_count = len(ocr)

        # TRIGGER 추정 (10초 구간 기준, score>=3 AND 2종 이상)
        # 간이 집계: 2종 이상 신호가 있는 10초 구간 수
        max_ts = 0
        for df in [yolo, clip, stt, ocr]:
            if "frame_ts" in df.columns and len(df) > 0:
                max_ts = max(max_ts, df["frame_ts"].max())
            if "start_ts" in df.columns and len(df) > 0:
                max_ts = max(max_ts, df["start_ts"].max())

        trigger_count = 0
        for t_start in range(0, int(max_ts) + 1, 10):
            t_end = t_start + 10
            signals = 0
            if len(yolo) > 0 and "frame_ts" in yolo.columns:
                if len(yolo[(yolo["frame_ts"] >= t_start) & (yolo["frame_ts"] < t_end)]) > 0:
                    signals += 1
            if len(clip) > 0 and "frame_ts" in clip.columns:
                if len(clip[(clip["frame_ts"] >= t_start) & (clip["frame_ts"] < t_end)]) > 0:
                    signals += 1
            if len(stt) > 0 and "start_ts" in stt.columns:
                if len(stt[(stt["start_ts"] < t_end) & (stt["end_ts"] > t_start)]) > 0:
                    signals += 1
            if len(ocr) > 0 and "frame_ts" in ocr.columns:
                if len(ocr[(ocr["frame_ts"] >= t_start) & (ocr["frame_ts"] < t_end)]) > 0:
                    signals += 1
            if signals >= 2:
                trigger_count += 1

        summaries.append({
            "vod_id": vod_id,
            "ad_categories": ad_categories,
            "primary_region": primary_region,
            "ad_regions": ad_regions,
            "trigger_count": trigger_count,
            "top_keywords": top_keywords,
            "ad_hints": ad_hints_list,
            "yolo_count": yolo_count,
            "clip_count": clip_count,
            "stt_count": stt_count,
            "ocr_count": ocr_count,
        })

    return summaries


def main():
    parser = argparse.ArgumentParser(description="VOD 요약 집계")
    parser.add_argument("--parquet-dir", type=str, default=str(DEFAULT_PARQUET_DIR))
    parser.add_argument("--output", type=str, default=str(OUTPUT_DIR / "vod_ad_summary.parquet"))
    args = parser.parse_args()

    parquet_dir = Path(args.parquet_dir)
    print(f"{'=' * 60}")
    print(f"  VOD 요약 집계")
    print(f"  입력: {parquet_dir}")
    print(f"{'=' * 60}")

    summaries = build_summary(parquet_dir)

    if not summaries:
        print("  ❌ 요약할 VOD 없음")
        return

    df = pd.DataFrame(summaries)

    # 리스트 컬럼을 JSON 문자열로 변환 (parquet 호환)
    for col in ["ad_categories", "ad_regions", "top_keywords", "ad_hints"]:
        df[col] = df[col].apply(json.dumps, ensure_ascii=False)

    df.to_parquet(args.output, index=False)
    print(f"\n  저장: {args.output} ({len(df)}건)")

    # 결과 출력
    print(f"\n{'=' * 60}")
    print(f"  VOD별 요약")
    print(f"{'=' * 60}")
    for _, row in df.iterrows():
        cats = json.loads(row["ad_categories"])
        regions = json.loads(row["ad_regions"])
        keywords = json.loads(row["top_keywords"])
        print(f"\n  {row['vod_id']}")
        print(f"    카테고리: {cats}")
        print(f"    지역: {row['primary_region']} ({regions})")
        print(f"    TRIGGER: {row['trigger_count']}건")
        print(f"    키워드: {keywords}")
        print(f"    신호: YOLO={row['yolo_count']} CLIP={row['clip_count']} STT={row['stt_count']} OCR={row['ocr_count']}")


if __name__ == "__main__":
    main()
