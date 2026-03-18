"""
pilot_clip_test.py — CLIP 파이프라인 파일럿 테스트 (트레일러 10건)

실행:
    cd Object_Detection
    python scripts/pilot_clip_test.py
    python scripts/pilot_clip_test.py --limit 5 --config config/clip_queries_ko.yaml
"""
import sys
import random
import argparse
import yaml
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
CONFIG_PATH  = PROJECT_ROOT / "config" / "clip_queries_ko.yaml"

from frame_extractor import extract_frames, list_video_files
from clip_scorer import ClipScorer
from context_filter import ContextFilter


def load_config(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def flatten_queries(config):
    queries = []
    for qs in config.get("queries", {}).values():
        queries.extend(qs)
    return queries


def build_query_category_map(config):
    mapping = {}
    for category, qs in config.get("queries", {}).items():
        for q in qs:
            mapping[q] = category
    return mapping


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=str, default=str(TRAILERS_DIR))
    parser.add_argument("--config",    type=str, default=str(CONFIG_PATH))
    parser.add_argument("--limit",     type=int, default=10)
    parser.add_argument("--fps",       type=float, default=1.0)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--seed",      type=int, default=42)
    parser.add_argument("--save-frames", action="store_true",
                        help="탐지된 프레임을 이미지로 저장 (data/pilot_frames/)")
    args = parser.parse_args()

    random.seed(args.seed)

    # 파일 로드
    video_files = list_video_files(args.input_dir)
    if not video_files:
        print(f"[ERROR] 영상 없음: {args.input_dir}")
        return

    sampled = random.sample(video_files, min(args.limit, len(video_files)))
    print(f"\n대상 트레일러: {len(sampled)}건 (전체 {len(video_files)}건 중 랜덤)")
    print(f"설정 파일: {args.config}\n")

    # 설정 로드
    config             = load_config(args.config)
    queries            = flatten_queries(config)
    query_category_map = build_query_category_map(config)
    threshold          = args.threshold if args.threshold is not None else config.get("threshold", 0.22)
    model_name         = config.get("model", "clip-ViT-B-32")

    print(f"쿼리 수: {len(queries)}개 | threshold: {threshold} | 모델: {model_name}")

    scorer     = ClipScorer(model_name=model_name)
    ctx_filter = ContextFilter()

    frames_out = PROJECT_ROOT / "data" / "pilot_frames"
    if args.save_frames:
        frames_out.mkdir(parents=True, exist_ok=True)
        print(f"프레임 저장 경로: {frames_out}\n")

    all_records = []
    category_hits = defaultdict(int)
    suppressed_frames = 0

    for i, video_path in enumerate(sampled):
        vod_id = video_path.stem
        print(f"\n[{i+1}/{len(sampled)}] {video_path.name}")

        try:
            frames, timestamps = extract_frames(str(video_path), fps=args.fps)
            # 프레임 인덱스 맵 (frame_ts → frame)
            ts_to_frame = {round(ts, 3): f for ts, f in zip(timestamps, frames)}

            results = scorer.score_frames(frames, queries)
            records = scorer.to_records(
                vod_id, timestamps, results,
                threshold=threshold,
                query_category_map=query_category_map,
            )

            # negative 억제로 제거된 프레임 수 계산
            total_frames_with_hits = sum(
                1 for ts_scores in results
                if any(s >= threshold for q, s in ts_scores.items()
                       if query_category_map.get(q) != "negative")
            )
            suppressed = total_frames_with_hits - len(set(r["frame_ts"] for r in records))
            suppressed_frames += max(0, suppressed)

            # context_filter 적용
            ts_to_scores = {round(ts, 3): sc for ts, sc in zip(timestamps, results)}
            for r in records:
                ctx = ctx_filter.validate(
                    yolo_labels=set(),
                    clip_scores=ts_to_scores.get(round(r["frame_ts"], 3), {}),
                    ad_category=r.get("ad_category", ""),
                )
                r["context_valid"]  = ctx["context_valid"]
                r["context_reason"] = ctx["context_reason"]

            valid_records = [r for r in records if r["context_valid"]]
            all_records.extend(valid_records)

            # VOD별 카테고리 히트 출력 + 프레임 저장
            hit_cats = defaultdict(list)
            for r in valid_records:
                hit_cats[r["ad_category"]].append(r["concept"])

                # 프레임 저장
                if args.save_frames:
                    import cv2
                    frame_key = round(r["frame_ts"], 3)
                    frame = ts_to_frame.get(frame_key)
                    if frame is not None:
                        safe_concept = r["concept"][:30].replace(" ", "_").replace("/", "-")
                        fname = f"{vod_id}__ts{r['frame_ts']:.1f}__{r['ad_category']}__{safe_concept}.jpg"
                        out_img = frames_out / fname
                        ret, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                        if ret:
                            buf.tofile(str(out_img))

            for cat, concepts in sorted(hit_cats.items()):
                top = sorted(set(concepts))[:3]
                print(f"  ✅ {cat}: {', '.join(top)}")
                category_hits[cat] += len(concepts)

            if not valid_records:
                print(f"  — 탐지 없음 (프레임 {len(frames)}개)")

        except Exception as e:
            print(f"  [ERROR] {e}")

    # ─── 전체 요약 ───────────────────────────────────────────
    print("\n" + "=" * 60)
    print(f"파일럿 결과 요약 — {len(sampled)}건 트레일러")
    print("=" * 60)
    print(f"총 탐지 레코드: {len(all_records)}건")
    print(f"negative 억제 프레임: {suppressed_frames}건")

    if all_records:
        df = pd.DataFrame(all_records)

        print(f"\n[카테고리별 히트 수]")
        for cat, cnt in sorted(category_hits.items(), key=lambda x: -x[1]):
            print(f"  {cat:<20} {cnt:>5}건")

        print(f"\n[상위 concept TOP 10]")
        top_concepts = df["concept"].value_counts().head(10)
        for concept, cnt in top_concepts.items():
            print(f"  {concept:<40} {cnt:>4}건")

        print(f"\n[VOD별 탐지 건수]")
        for vod_id, cnt in df.groupby("vod_id").size().sort_values(ascending=False).items():
            print(f"  {vod_id:<40} {cnt:>4}건")

        # parquet 저장
        out_path = PROJECT_ROOT / "data" / "pilot_clip_result.parquet"
        out_path.parent.mkdir(exist_ok=True)
        df.to_parquet(str(out_path), index=False)
        print(f"\n결과 저장: {out_path}")
    else:
        print("\n탐지 결과 없음 — threshold 낮춰보거나 쿼리 확인 필요")
        print(f"  현재 threshold: {threshold}")
        print(f"  힌트: --threshold 0.15 로 낮춰서 재시도")


if __name__ == "__main__":
    main()
