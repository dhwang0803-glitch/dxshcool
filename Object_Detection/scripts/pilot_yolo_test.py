"""
pilot_yolo_test.py — base YOLO 파일럿 테스트 (트레일러 10건, bbox 시각화)

실행:
    cd Object_Detection
    python scripts/pilot_yolo_test.py
    python scripts/pilot_yolo_test.py --limit 5 --fps 0.3
"""
import sys
import random
import argparse
import cv2
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TRAILERS_DIR = PROJECT_ROOT.parent / "VOD_Embedding" / "data" / "trailers_아름"

from frame_extractor import extract_frames, list_video_files
from detector import Detector

# 카테고리별 색상 (BGR)
CATEGORY_COLORS = {
    "가전":    (0, 165, 255),   # 주황
    "가구":    (0, 255, 0),     # 초록
    "주방":    (255, 0, 0),     # 파랑
    "패션":    (255, 0, 255),   # 보라
    "음식":    (0, 255, 255),   # 노랑
    "기타":    (128, 128, 128), # 회색
}

# COCO 라벨 → 광고 카테고리 매핑
LABEL_TO_AD = {
    "tv":           "가전",
    "laptop":       "가전",
    "cell phone":   "가전",
    "microwave":    "가전",
    "oven":         "가전",
    "refrigerator": "가전",
    "toaster":      "가전",
    "couch":        "가구",
    "chair":        "가구",
    "bed":          "가구",
    "dining table": "가구",
    "sink":         "주방",
    "fork":         "주방",
    "knife":        "주방",
    "spoon":        "주방",
    "bowl":         "주방",
    "cup":          "주방",
    "bottle":       "주방",
    "handbag":      "패션",
    "backpack":     "패션",
    "suitcase":     "패션",
    "tie":          "패션",
    "umbrella":     "패션",
    "pizza":        "음식",
    "hot dog":      "음식",
    "sandwich":     "음식",
    "cake":         "음식",
    "donut":        "음식",
    "apple":        "음식",
    "banana":       "음식",
    "orange":       "음식",
}

AD_LABELS = set(LABEL_TO_AD.keys())


def draw_boxes(frame, boxes, min_conf=0.5):
    """탐지된 bbox를 프레임에 그려서 반환."""
    img = frame.copy()
    for box in boxes:
        if box["confidence"] < min_conf:
            continue
        label = box["label"]
        ad_cat = LABEL_TO_AD.get(label, "기타")
        color = CATEGORY_COLORS.get(ad_cat, (128, 128, 128))
        x1, y1, x2, y2 = [int(v) for v in box["bbox"]]

        cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {box['confidence']:.2f} [{ad_cat}]"
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(img, (x1, y1 - th - 4), (x1 + tw, y1), color, -1)
        cv2.putText(img, text, (x1, y1 - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
    return img


def save_frame(img, out_dir, vod_id, ts, boxes):
    """광고 연관 라벨이 있는 프레임만 저장."""
    ad_labels = [b["label"] for b in boxes if b["label"] in AD_LABELS]
    if not ad_labels:
        return
    tag = "_".join(sorted(set(ad_labels)))[:50]
    fname = f"{vod_id}__ts{ts:.1f}__{tag}.jpg"
    out_path = out_dir / fname
    ret, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
    if ret:
        buf.tofile(str(out_path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=str, default=str(TRAILERS_DIR))
    parser.add_argument("--model",     type=str, default="yolo11s.pt")
    parser.add_argument("--limit",     type=int, default=10)
    parser.add_argument("--fps",       type=float, default=0.3)
    parser.add_argument("--conf",      type=float, default=0.5)
    parser.add_argument("--seed",      type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    video_files = list_video_files(args.input_dir)
    if not video_files:
        print(f"[ERROR] 영상 없음: {args.input_dir}")
        return

    sampled = random.sample(video_files, min(args.limit, len(video_files)))
    print(f"\n대상: {len(sampled)}건 | 모델: {args.model} | fps: {args.fps} | conf: {args.conf}")

    out_dir = PROJECT_ROOT / "data" / "pilot_yolo_frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"저장 경로: {out_dir}\n")

    det = Detector(model_name=args.model, confidence=args.conf)
    all_records = []
    label_hits = defaultdict(int)

    for i, video_path in enumerate(sampled):
        vod_id = video_path.stem
        print(f"[{i+1}/{len(sampled)}] {video_path.name}")

        try:
            frames, timestamps = extract_frames(str(video_path), fps=args.fps)
            results = det.infer(frames, timestamps)

            for item, frame in zip(results, frames):
                ts = item["frame_ts"]
                boxes = item["boxes"]
                ad_boxes = [b for b in boxes if b["label"] in AD_LABELS]

                if ad_boxes:
                    img = draw_boxes(frame, boxes)
                    save_frame(img, out_dir, vod_id, ts, boxes)
                    for b in ad_boxes:
                        label_hits[b["label"]] += 1
                        all_records.append({
                            "vod_id": vod_id,
                            "frame_ts": ts,
                            "label": b["label"],
                            "confidence": b["confidence"],
                            "ad_category": LABEL_TO_AD[b["label"]],
                        })

            ad_count = len([r for r in all_records if r["vod_id"] == vod_id])
            if ad_count > 0:
                cats = set(LABEL_TO_AD[b["label"]] for item in results
                           for b in item["boxes"] if b["label"] in AD_LABELS)
                print(f"  ✅ 광고 연관 탐지 {ad_count}건: {', '.join(cats)}")
            else:
                print(f"  — 광고 연관 탐지 없음 (프레임 {len(frames)}개)")

        except Exception as e:
            print(f"  [ERROR] {e}")

    # 요약
    print("\n" + "=" * 50)
    print(f"결과 요약 — {len(sampled)}건 트레일러")
    print("=" * 50)
    print(f"광고 연관 프레임: {len(set((r['vod_id'], r['frame_ts']) for r in all_records))}개")
    print(f"총 탐지 레코드:  {len(all_records)}건")

    if label_hits:
        print(f"\n[라벨별 탐지 수]")
        for label, cnt in sorted(label_hits.items(), key=lambda x: -x[1]):
            cat = LABEL_TO_AD[label]
            print(f"  {label:<20} [{cat}]  {cnt}건")

        df = pd.DataFrame(all_records)
        out_path = PROJECT_ROOT / "data" / "pilot_yolo_result.parquet"
        df.to_parquet(str(out_path), index=False)
        print(f"\n결과 저장: {out_path}")
    else:
        print("\n광고 연관 탐지 없음")

    print(f"프레임 이미지: {out_dir}")


if __name__ == "__main__":
    main()
