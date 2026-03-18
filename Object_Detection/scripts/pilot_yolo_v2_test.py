"""
pilot_yolo_v2_test.py — YOLO v2 (COCO 사전필터 + 파인튜닝) 테스트

COCO 모델로 음식 컨텍스트(bowl, cup, fork 등) 확인 후,
파인튜닝 모델 결과를 채택/탈락 판정.

실행:
    cd Object_Detection
    python scripts/pilot_yolo_v2_test.py --save-frames --conf 0.5 --videos file1.mp4 file2.mp4
"""
import sys
import random
import argparse
from pathlib import Path
from collections import defaultdict

import cv2
import numpy as np
import pandas as pd
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from frame_extractor import extract_frames, list_video_files
from detector_v2 import DetectorV2

TRAILERS_DIR = PROJECT_ROOT.parent / "VOD_Embedding" / "data" / "trailers_아름"
BEST_PT = PROJECT_ROOT / "models" / "best.pt"
COCO_PT = "yolo11s.pt"


_FONT_CACHE = {}

def _get_korean_font(size=20):
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    font_paths = [
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/malgun.ttf",
        "C:/Windows/Fonts/NanumGothicBold.ttf",
        "C:/Windows/Fonts/gulim.ttc",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, size, encoding="unic")
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue
    font = ImageFont.load_default()
    _FONT_CACHE[size] = font
    return font


def draw_boxes(frame, boxes, color, label_prefix=""):
    """프레임에 바운딩 박스 + 한국어 라벨 그리기 (PIL)"""
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = _get_korean_font(20)
    rgb_color = (color[2], color[1], color[0])

    for b in boxes:
        x1, y1, x2, y2 = [int(v) for v in b["bbox"]]
        conf = b["confidence"]
        label = f"{label_prefix}{b['label']} {conf:.2f}"
        draw.rectangle([x1, y1, x2, y2], outline=rgb_color, width=3)
        left, top, right, bottom = font.getbbox(label)
        tw, th = right - left, bottom - top
        bg_y1 = max(y1 - th - 8, 0)
        draw.rectangle([x1, bg_y1, x1 + tw + 8, bg_y1 + th + 6], fill=rgb_color)
        draw.text((x1 + 4, bg_y1 + 2), label, fill=(255, 255, 255), font=font)

    out = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return out


def draw_info(frame, coco_objects, food_context):
    """프레임 하단에 COCO 탐지 정보 표시"""
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = _get_korean_font(16)

    h = pil_img.height
    ctx_text = "✅ 음식 컨텍스트" if food_context else "❌ 음식 컨텍스트 없음"
    coco_text = f"COCO: {', '.join(coco_objects[:5])}" if coco_objects else "COCO: (없음)"
    info = f"{ctx_text} | {coco_text}"

    left, top, right, bottom = font.getbbox(info)
    tw, th = right - left, bottom - top
    draw.rectangle([0, h - th - 10, tw + 12, h], fill=(0, 0, 0))
    draw.text((6, h - th - 6), info, fill=(255, 255, 255), font=font)

    out = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return out


def main():
    parser = argparse.ArgumentParser(description="YOLO v2 테스트 (COCO 사전필터)")
    parser.add_argument("--input-dir", type=str, default=str(TRAILERS_DIR))
    parser.add_argument("--best-pt", type=str, default=str(BEST_PT))
    parser.add_argument("--coco-pt", type=str, default=COCO_PT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--conf", type=float, default=0.5,
                        help="파인튜닝 모델 confidence threshold (default: 0.5)")
    parser.add_argument("--coco-conf", type=float, default=0.3,
                        help="COCO 모델 confidence threshold (default: 0.3)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-frames", action="store_true")
    parser.add_argument("--videos", nargs="+", type=str, default=None)
    args = parser.parse_args()

    random.seed(args.seed)

    print("=" * 60)
    print("YOLO v2 테스트 (COCO 사전필터 + 파인튜닝)")
    print("=" * 60)

    if not Path(args.best_pt).exists():
        print(f"[ERROR] best.pt 없음: {args.best_pt}")
        return

    print(f"\n파인튜닝 모델: {args.best_pt}")
    print(f"COCO 모델: {args.coco_pt}")
    detector = DetectorV2(
        food_model=args.best_pt,
        coco_model=args.coco_pt,
        confidence=args.conf,
        coco_confidence=args.coco_conf,
        device="cpu",
    )
    print(f"파인튜닝 클래스 수: {len(detector.food_detector.model.names)}")
    print(f"conf: food={args.conf} / coco={args.coco_conf}")

    # 영상 로드
    if args.videos:
        input_dir = Path(args.input_dir)
        sampled = []
        for v in args.videos:
            p = Path(v)
            if p.exists():
                sampled.append(p)
            elif (input_dir / v).exists():
                sampled.append(input_dir / v)
            else:
                print(f"[WARN] 파일 없음: {v}")
        if not sampled:
            print("[ERROR] 유효한 영상 파일 없음")
            return
    else:
        video_files = list_video_files(args.input_dir)
        if not video_files:
            print(f"\n[ERROR] 영상 없음: {args.input_dir}")
            return
        sampled = random.sample(video_files, min(args.limit, len(video_files)))

    print(f"\n대상 트레일러: {len(sampled)}건")

    frames_dir = PROJECT_ROOT / "data" / "v2_test_frames"
    if args.save_frames:
        frames_dir.mkdir(parents=True, exist_ok=True)
        print(f"프레임 저장: {frames_dir}")

    # 결과 수집
    all_records = []
    label_hits = defaultdict(int)
    stats = {"total_frames": 0, "food_context_frames": 0,
             "detected": 0, "filtered": 0}

    for i, video_path in enumerate(sampled):
        vod_id = video_path.stem
        print(f"\n{'─' * 50}")
        print(f"[{i+1}/{len(sampled)}] {video_path.name}")

        try:
            frames, timestamps = extract_frames(str(video_path), fps=args.fps)
            print(f"  프레임: {len(frames)}개")
        except Exception as e:
            print(f"  [ERROR] 프레임 추출 실패: {e}")
            continue

        results = detector.infer(frames, timestamps)
        records = detector.to_records(vod_id, results)
        all_records.extend(records)

        # 통계
        for item in results:
            stats["total_frames"] += 1
            if item["food_context"]:
                stats["food_context_frames"] += 1

        # v1 대비 필터링 효과 — 파인튜닝 모델이 잡았지만 컨텍스트 없어서 버린 것
        food_preds = detector.food_detector(
            frames[0], conf=args.conf, device="cpu", verbose=False
        ) if frames else []

        labels = defaultdict(int)
        for r in records:
            labels[r["label"]] += 1
            label_hits[r["label"]] += 1

        detected_count = len(records)
        stats["detected"] += detected_count

        print(f"  탐지: {detected_count}건 (COCO 필터 통과)")
        for label, cnt in sorted(labels.items(), key=lambda x: -x[1])[:10]:
            print(f"    {label:<20} {cnt:>3}건")

        # COCO 컨텍스트 요약
        ctx_frames = sum(1 for item in results if item["food_context"])
        print(f"  COCO 음식 컨텍스트: {ctx_frames}/{len(frames)} 프레임")

        # 프레임 저장
        if args.save_frames:
            ts_to_frame = {round(ts, 3): f for ts, f in zip(timestamps, frames)}
            saved = set()
            for item in results:
                fkey = round(item["frame_ts"], 3)
                if fkey in saved:
                    continue
                frame = ts_to_frame.get(fkey)
                if frame is None:
                    continue

                # 탐지 있는 프레임 or 음식 컨텍스트 있는 프레임
                if item["boxes"] or item["food_context"]:
                    out = frame.copy()
                    if item["boxes"]:
                        out = draw_boxes(out, item["boxes"], (0, 255, 0), "[v2] ")
                    out = draw_info(out, item["coco_objects"], item["food_context"])

                    suffix = "HIT" if item["boxes"] else "CTX"
                    fname = f"{vod_id}__ts{item['frame_ts']:.1f}__{suffix}.jpg"
                    ret, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
                    if ret:
                        buf.tofile(str(frames_dir / fname))
                    saved.add(fkey)

    # 전체 요약
    print("\n" + "=" * 60)
    print("v2 테스트 결과 요약")
    print("=" * 60)
    print(f"\n총 프레임: {stats['total_frames']}")
    print(f"COCO 음식 컨텍스트 프레임: {stats['food_context_frames']} "
          f"({stats['food_context_frames']/max(stats['total_frames'],1)*100:.1f}%)")
    print(f"최종 탐지: {stats['detected']}건")

    if label_hits:
        print(f"\n상위 라벨:")
        for label, cnt in sorted(label_hits.items(), key=lambda x: -x[1])[:20]:
            print(f"  {label:<25} {cnt:>5}건")

    # parquet 저장
    out_dir = PROJECT_ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    if all_records:
        df = pd.DataFrame(all_records)
        path = out_dir / "v2_test_results.parquet"
        df.to_parquet(str(path), index=False)
        print(f"\n결과 저장: {path}")

    print("\n완료!")


if __name__ == "__main__":
    main()
