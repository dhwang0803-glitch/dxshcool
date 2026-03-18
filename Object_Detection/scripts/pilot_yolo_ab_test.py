"""
pilot_yolo_ab_test.py — YOLO 파인튜닝 모델 A/B 테스트

best.pt(파인튜닝) vs yolo11s.pt(기본) 동일 트레일러에서 비교.
탐지 결과를 콘솔 출력 + 프레임 이미지 저장(선택).

실행:
    cd Object_Detection
    python scripts/pilot_yolo_ab_test.py
    python scripts/pilot_yolo_ab_test.py --limit 5 --save-frames
    python scripts/pilot_yolo_ab_test.py --input-dir /path/to/videos --conf 0.3
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
from detector import Detector

TRAILERS_DIR = PROJECT_ROOT.parent / "VOD_Embedding" / "data" / "trailers_아름"
BEST_PT = PROJECT_ROOT / "models" / "best.pt"
BASE_PT = "yolo11s.pt"


_FONT_CACHE = {}

def _get_korean_font(size=20):
    """한국어 지원 폰트 로드 (캐시)"""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    font_paths = [
        "C:/Windows/Fonts/malgunbd.ttf",    # 맑은 고딕 Bold
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/NanumGothicBold.ttf",
        "C:/Windows/Fonts/gulim.ttc",        # 굴림
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
    """프레임에 바운딩 박스 + 한국어 라벨 그리기 (PIL 사용)"""
    # BGR → RGB → PIL
    pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil_img)
    font = _get_korean_font(20)
    # color는 BGR tuple → RGB로 변환
    rgb_color = (color[2], color[1], color[0])

    for b in boxes:
        x1, y1, x2, y2 = [int(v) for v in b["bbox"]]
        conf = b["confidence"]
        label = f"{label_prefix}{b['label']} {conf:.2f}"
        # bbox
        draw.rectangle([x1, y1, x2, y2], outline=rgb_color, width=3)
        # 텍스트 크기 측정
        left, top, right, bottom = font.getbbox(label)
        tw, th = right - left, bottom - top
        # 텍스트 배경 (bbox 위에)
        bg_y1 = max(y1 - th - 8, 0)
        draw.rectangle([x1, bg_y1, x1 + tw + 8, bg_y1 + th + 6], fill=rgb_color)
        draw.text((x1 + 4, bg_y1 + 2), label, fill=(255, 255, 255), font=font)

    # PIL → BGR numpy
    out = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return out


def main():
    parser = argparse.ArgumentParser(description="YOLO 파인튜닝 A/B 테스트")
    parser.add_argument("--input-dir", type=str, default=str(TRAILERS_DIR))
    parser.add_argument("--best-pt", type=str, default=str(BEST_PT))
    parser.add_argument("--base-pt", type=str, default=BASE_PT)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--conf", type=float, default=0.4,
                        help="confidence threshold (default: 0.4)")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--save-frames", action="store_true",
                        help="탐지 프레임 이미지 저장 (data/ab_test_frames/)")
    parser.add_argument("--best-only", action="store_true",
                        help="파인튜닝 모델만 테스트 (기본 모델 스킵)")
    parser.add_argument("--videos", nargs="+", type=str, default=None,
                        help="테스트할 영상 파일 직접 지정 (경로 또는 파일명)")
    args = parser.parse_args()

    random.seed(args.seed)

    # 모델 로드
    print("=" * 60)
    print("YOLO A/B 테스트")
    print("=" * 60)

    if not Path(args.best_pt).exists():
        print(f"[ERROR] best.pt 없음: {args.best_pt}")
        return

    print(f"\n[A] 파인튜닝 모델: {args.best_pt}")
    model_a = Detector(model_name=args.best_pt, confidence=args.conf)
    print(f"    클래스 수: {len(model_a.model.names)}")
    print(f"    라벨 예시: {dict(list(model_a.model.names.items())[:5])}")

    model_b = None
    if not args.best_only:
        print(f"\n[B] 기본 모델: {args.base_pt}")
        model_b = Detector(model_name=args.base_pt, confidence=args.conf)
        print(f"    클래스 수: {len(model_b.model.names)}")

    # 영상 로드
    if args.videos:
        # 직접 지정된 파일 사용
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
    total = len(video_files) if not args.videos else len(sampled)
    print(f"\n대상 트레일러: {len(sampled)}건 (전체 {total}건 중)")
    print(f"conf threshold: {args.conf} | fps: {args.fps}")

    frames_dir = PROJECT_ROOT / "data" / "ab_test_frames"
    if args.save_frames:
        frames_dir.mkdir(parents=True, exist_ok=True)
        print(f"프레임 저장: {frames_dir}")

    # 결과 수집
    records_a, records_b = [], []
    cat_hits_a, cat_hits_b = defaultdict(int), defaultdict(int)

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

        # ── Model A (파인튜닝) ──
        res_a = model_a.infer(frames, timestamps)
        recs_a = model_a.to_records(vod_id, res_a)
        records_a.extend(recs_a)

        labels_a = defaultdict(int)
        for r in recs_a:
            labels_a[r["label"]] += 1
            cat_hits_a[r["label"]] += 1

        print(f"\n  [A] 파인튜닝 — {len(recs_a)}건 탐지")
        for label, cnt in sorted(labels_a.items(), key=lambda x: -x[1])[:10]:
            print(f"      {label:<20} {cnt:>3}건")

        # ── Model B (기본) ──
        if model_b:
            res_b = model_b.infer(frames, timestamps)
            recs_b = model_b.to_records(vod_id, res_b)
            records_b.extend(recs_b)

            labels_b = defaultdict(int)
            for r in recs_b:
                labels_b[r["label"]] += 1
                cat_hits_b[r["label"]] += 1

            print(f"  [B] 기본     — {len(recs_b)}건 탐지")
            for label, cnt in sorted(labels_b.items(), key=lambda x: -x[1])[:10]:
                print(f"      {label:<20} {cnt:>3}건")

        # ── 프레임 저장 ──
        if args.save_frames:
            ts_to_frame = {round(ts, 3): f for ts, f in zip(timestamps, frames)}
            # 탐지 있는 프레임만 저장
            saved = set()
            for r in recs_a:
                fkey = round(r["frame_ts"], 3)
                if fkey in saved:
                    continue
                frame = ts_to_frame.get(fkey)
                if frame is None:
                    continue
                boxes_a = [b for item in res_a
                           if round(item["frame_ts"], 3) == fkey
                           for b in item["boxes"]]
                out = draw_boxes(frame, boxes_a, (0, 255, 0), "[A] ")
                fname = f"{vod_id}__ts{r['frame_ts']:.1f}__A.jpg"
                ret, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if ret:
                    buf.tofile(str(frames_dir / fname))
                saved.add(fkey)

    # ── 전체 요약 ──
    print("\n" + "=" * 60)
    print("A/B 테스트 결과 요약")
    print("=" * 60)

    print(f"\n[A] 파인튜닝 (best.pt)")
    print(f"  총 탐지: {len(records_a)}건")
    if cat_hits_a:
        print(f"  상위 라벨:")
        for label, cnt in sorted(cat_hits_a.items(), key=lambda x: -x[1])[:15]:
            print(f"    {label:<20} {cnt:>5}건")

    if model_b:
        print(f"\n[B] 기본 (yolo11s.pt)")
        print(f"  총 탐지: {len(records_b)}건")
        if cat_hits_b:
            print(f"  상위 라벨:")
            for label, cnt in sorted(cat_hits_b.items(), key=lambda x: -x[1])[:15]:
                print(f"    {label:<20} {cnt:>5}건")

        print(f"\n[비교]")
        print(f"  A 탐지 건수: {len(records_a)}  |  B 탐지 건수: {len(records_b)}")
        if records_b:
            ratio = len(records_a) / max(len(records_b), 1)
            print(f"  A/B 비율: {ratio:.2f}x")

    # parquet 저장
    out_dir = PROJECT_ROOT / "data"
    out_dir.mkdir(exist_ok=True)

    if records_a:
        df_a = pd.DataFrame(records_a)
        path_a = out_dir / "ab_test_model_a.parquet"
        df_a.to_parquet(str(path_a), index=False)
        print(f"\n[A] 결과 저장: {path_a}")

    if records_b:
        df_b = pd.DataFrame(records_b)
        path_b = out_dir / "ab_test_model_b.parquet"
        df_b.to_parquet(str(path_b), index=False)
        print(f"[B] 결과 저장: {path_b}")

    print("\n완료!")


if __name__ == "__main__":
    main()
