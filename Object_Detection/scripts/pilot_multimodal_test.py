"""
pilot_multimodal_test.py — YOLO + CLIP + STT 3종 통합 파일럿 테스트

각 신호가 동일 영상에서 뭘 잡는지 비교하고,
멀티시그널 스코어링으로 광고 트리거 구간을 산출한다.

실행:
    cd Object_Detection
    python scripts/pilot_multimodal_test.py --videos video1.mp4 video2.mp4
"""
import sys
import os
import random
import argparse
from pathlib import Path
from collections import defaultdict

import yaml
import pandas as pd
import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from frame_extractor import extract_frames, list_video_files
from detector_v2 import DetectorV2
from clip_scorer import ClipScorer
from audio_extractor import AudioExtractor
from stt_scorer import SttScorer
from keyword_mapper import KeywordMapper
from ocr_scorer import OcrScorer

TRAILERS_DIR = PROJECT_ROOT.parent / "VOD_Embedding" / "data" / "trailers_아름"
BEST_PT = PROJECT_ROOT / "models" / "best.pt"
COCO_PT = "yolo11s.pt"
CLIP_QUERIES_PATH = PROJECT_ROOT / "config" / "clip_queries_ko.yaml"
STT_KEYWORDS_PATH = PROJECT_ROOT / "config" / "stt_keywords.yaml"


def load_clip_queries(path):
    """clip_queries_ko.yaml → (queries, query_category_map)"""
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # 최상위 'queries' 키가 있으면 그 아래를 사용
    if "queries" in config:
        config = config["queries"]
    queries = []
    qmap = {}
    for category, q_list in config.items():
        if not isinstance(q_list, list):
            continue
        for q in q_list:
            if isinstance(q, str):
                queries.append(q)
                qmap[q] = category
    return queries, qmap


def format_time(sec):
    m, s = divmod(int(sec), 60)
    return f"{m:02d}:{s:02d}"


def main():
    parser = argparse.ArgumentParser(description="YOLO+CLIP+STT 3종 통합 테스트")
    parser.add_argument("--videos", nargs="+", type=str, required=True)
    parser.add_argument("--input-dir", type=str, default=str(TRAILERS_DIR))
    parser.add_argument("--best-pt", type=str, default=str(BEST_PT))
    parser.add_argument("--yolo-conf", type=float, default=0.5)
    parser.add_argument("--clip-threshold", type=float, default=0.30)
    parser.add_argument("--whisper-model", type=str, default="small")
    parser.add_argument("--fps", type=float, default=1.0)
    parser.add_argument("--save-frames", action="store_true",
                        help="TRIGGER 구간 대표 프레임을 이미지로 저장")
    args = parser.parse_args()

    print("=" * 70)
    print("  YOLO + CLIP + STT 멀티모달 통합 테스트")
    print("=" * 70)

    # ── 모델 로드 ──
    print("\n[1/5] 모델 로드 중...")

    print("  YOLO v2 (COCO 필터 + 파인튜닝)...")
    yolo = DetectorV2(
        food_model=args.best_pt,
        coco_model=COCO_PT,
        confidence=args.yolo_conf,
        coco_confidence=0.3,
        device="cpu",
    )
    print(f"  → 파인튜닝 {len(yolo.food_detector.model.names)}종 메뉴")

    print("  CLIP (multilingual)...")
    clip = ClipScorer("clip-ViT-B-32-multilingual-v1")
    queries, qmap = load_clip_queries(CLIP_QUERIES_PATH)
    print(f"  → {len(queries)}개 쿼리")

    print("  Whisper STT ({})...".format(args.whisper_model))
    audio_ext = AudioExtractor()
    stt = SttScorer(args.whisper_model)
    kw_mapper = KeywordMapper(str(STT_KEYWORDS_PATH))

    print("  EasyOCR (한국어+영어)...")
    ocr = OcrScorer(["ko", "en"])
    print("  → 로드 완료")

    # ── 영상 처리 ──
    input_dir = Path(args.input_dir)
    video_paths = []
    for v in args.videos:
        p = Path(v)
        if p.exists():
            video_paths.append(p)
        elif (input_dir / v).exists():
            video_paths.append(input_dir / v)
        else:
            print(f"[WARN] 파일 없음: {v}")

    if not video_paths:
        print("[ERROR] 유효한 영상 없음")
        return

    print(f"\n대상: {len(video_paths)}건")

    all_results = []

    for vi, video_path in enumerate(video_paths):
        vod_id = video_path.stem
        print(f"\n{'━' * 70}")
        print(f"[{vi+1}/{len(video_paths)}] {video_path.name}")
        print(f"{'━' * 70}")

        # 프레임 추출
        try:
            frames, timestamps = extract_frames(str(video_path), fps=args.fps)
            print(f"  프레임: {len(frames)}개 ({format_time(timestamps[-1])} 길이)")
        except Exception as e:
            print(f"  [ERROR] 프레임 추출 실패: {e}")
            continue

        # ── YOLO v2 ──
        print("\n  [YOLO v2] 추론 중...")
        yolo_results = yolo.infer(frames, timestamps)
        yolo_records = yolo.to_records(vod_id, yolo_results)
        yolo_labels = defaultdict(int)
        for r in yolo_records:
            yolo_labels[r["label"]] += 1

        ctx_frames = sum(1 for item in yolo_results if item["food_context"])
        print(f"  → COCO 음식 컨텍스트: {ctx_frames}/{len(frames)} 프레임")
        print(f"  → 탐지: {len(yolo_records)}건")
        for label, cnt in sorted(yolo_labels.items(), key=lambda x: -x[1])[:5]:
            print(f"    {label:<25} {cnt:>3}건")

        # ── CLIP ──
        print("\n  [CLIP] 스코어링 중...")
        clip_scores = clip.score_frames(frames, queries)
        clip_records = clip.to_records(
            vod_id, timestamps, clip_scores,
            threshold=args.clip_threshold,
            query_category_map=qmap,
        )
        clip_categories = defaultdict(int)
        for r in clip_records:
            clip_categories[r["ad_category"]] += 1

        print(f"  → 매칭: {len(clip_records)}건")
        for cat, cnt in sorted(clip_categories.items(), key=lambda x: -x[1])[:5]:
            print(f"    {cat:<25} {cnt:>3}건")

        # ── STT ──
        print("\n  [STT] 음성 인식 중...")
        try:
            wav_path = audio_ext.extract(str(video_path))
            segments = stt.transcribe(wav_path)
            os.unlink(wav_path)
        except Exception as e:
            print(f"  [ERROR] STT 실패: {e}")
            segments = []

        stt_records = []
        for seg in segments:
            matches = kw_mapper.match(seg["text"], vod_id, seg["start"], seg["end"])
            stt_records.extend(matches)

        print(f"  → 음성 구간: {len(segments)}개")
        print(f"  → 키워드 매칭: {len(stt_records)}건")
        for r in stt_records:
            print(f"    [{format_time(r['start_ts'])}~{format_time(r['end_ts'])}] "
                  f"\"{r['keyword']}\" → {r['ad_category']} "
                  f"| \"{r['transcript'][:40]}\"")

        # ── OCR ──
        print("\n  [OCR] 자막 인식 중...")
        ocr_results = ocr.extract_texts(frames, timestamps, sample_interval=3)
        # OCR 텍스트에서도 키워드 매칭 (1글자 키워드는 OCR에서 제외 — 오탐 방지)
        ocr_records = []
        for ocr_item in ocr_results:
            matches = kw_mapper.match(
                ocr_item["text"], vod_id,
                ocr_item["frame_ts"], ocr_item["frame_ts"] + 1.0
            )
            for m in matches:
                if len(m["keyword"]) >= 2:  # OCR은 2글자 이상만
                    ocr_records.append(m)

        print(f"  → OCR 프레임: {len(ocr_results)}개 (텍스트 있는 것만)")
        print(f"  → 키워드 매칭: {len(ocr_records)}건")
        for r in ocr_records[:10]:
            print(f"    [{format_time(r['start_ts'])}] "
                  f"\"{r['keyword']}\" → {r['ad_category']} "
                  f"| \"{r['transcript'][:40]}\"")
        if len(ocr_records) > 10:
            print(f"    ... +{len(ocr_records)-10}건")

        # ── 구간별 멀티시그널 요약 ──
        print(f"\n  {'─' * 60}")
        print(f"  멀티시그널 요약 (10초 구간)")
        print(f"  {'─' * 60}")

        # TRIGGER 프레임 저장용 디렉토리
        if args.save_frames:
            snap_dir = PROJECT_ROOT / "data" / "trigger_frames" / vod_id
            snap_dir.mkdir(parents=True, exist_ok=True)

        duration = timestamps[-1] if timestamps else 0
        interval = 10  # 10초 단위
        trigger_count = 0
        for t_start in range(0, int(duration) + 1, interval):
            t_end = t_start + interval
            score = 0
            signals = []

            # YOLO 체크
            yolo_in_range = [r for r in yolo_records
                             if t_start <= r["frame_ts"] < t_end]
            if yolo_in_range:
                score += 3
                labels_here = set(r["label"] for r in yolo_in_range)
                signals.append(f"YOLO: {', '.join(list(labels_here)[:2])}")

            # STT 체크
            stt_in_range = [r for r in stt_records
                            if r["start_ts"] < t_end and r["end_ts"] > t_start]
            if stt_in_range:
                score += 3
                kws = set(r["keyword"] for r in stt_in_range)
                signals.append(f"STT: {', '.join(kws)}")

            # CLIP 체크
            clip_in_range = [r for r in clip_records
                             if t_start <= r["frame_ts"] < t_end]
            if clip_in_range:
                score += 1
                cats = set(r["ad_category"] for r in clip_in_range)
                signals.append(f"CLIP: {', '.join(list(cats)[:2])}")

            # OCR 체크
            ocr_in_range = [r for r in ocr_records
                            if t_start <= r["start_ts"] < t_end]
            if ocr_in_range:
                score += 2
                ocr_kws = set(r["keyword"] for r in ocr_in_range)
                signals.append(f"OCR: {', '.join(list(ocr_kws)[:3])}")

            if signals:
                # 신호 종류 수 체크 (최소 2종 이상이어야 TRIGGER)
                n_signal_types = (1 if yolo_in_range else 0) + \
                                 (1 if stt_in_range else 0) + \
                                 (1 if clip_in_range else 0) + \
                                 (1 if ocr_in_range else 0)
                if score >= 3 and n_signal_types >= 2:
                    trigger = "🔥 TRIGGER"
                elif score >= 3 and n_signal_types == 1:
                    trigger = "⚠️ 단독 (교차검증 미충족)"
                else:
                    trigger = "  (약함)"
                print(f"  [{format_time(t_start)}~{format_time(t_end)}] "
                      f"score={score} [{n_signal_types}종] {trigger}")
                for s in signals:
                    print(f"    {s}")

                # ── TRIGGER 프레임 이미지 저장 ──
                if args.save_frames and score >= 3 and n_signal_types >= 2:
                    trigger_count += 1
                    # 구간 중앙 타임스탬프에 가장 가까운 프레임 선택
                    mid_ts = (t_start + t_end) / 2
                    best_idx = min(range(len(timestamps)),
                                   key=lambda i: abs(timestamps[i] - mid_ts))
                    frame = frames[best_idx].copy()

                    # 상단에 정보 오버레이
                    h, w = frame.shape[:2]
                    overlay = frame.copy()
                    cv2.rectangle(overlay, (0, 0), (w, 90), (0, 0, 0), -1)
                    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

                    label_text = f"[{format_time(t_start)}~{format_time(t_end)}] score={score} [{n_signal_types}sig]"
                    cv2.putText(frame, label_text, (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
                    sig_text = " | ".join(signals)
                    # 긴 텍스트는 잘라서 표시
                    cv2.putText(frame, sig_text[:80], (10, 65),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

                    fname = f"trigger_{t_start:04d}_{format_time(t_start)}_score{score}.jpg"
                    cv2.imwrite(str(snap_dir / fname), frame)

        if args.save_frames and trigger_count > 0:
            print(f"\n  📸 TRIGGER 프레임 {trigger_count}장 저장 → {snap_dir}")

        # 결과 저장
        all_results.append({
            "vod_id": vod_id,
            "filename": video_path.name,
            "yolo_count": len(yolo_records),
            "clip_count": len(clip_records),
            "stt_count": len(stt_records),
            "ocr_count": len(ocr_records),
            "food_context_frames": ctx_frames,
            "total_frames": len(frames),
        })

    # ── 전체 요약 ──
    print(f"\n{'━' * 70}")
    print("전체 요약")
    print(f"{'━' * 70}")
    print(f"\n{'VOD':<35} {'YOLO':>6} {'CLIP':>6} {'STT':>6} {'OCR':>6}")
    print(f"{'─' * 35} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6}")
    for r in all_results:
        name = r["filename"][:33]
        print(f"{name:<35} {r['yolo_count']:>6} {r['clip_count']:>6} "
              f"{r['stt_count']:>6} {r['ocr_count']:>6}")

    total_yolo = sum(r["yolo_count"] for r in all_results)
    total_clip = sum(r["clip_count"] for r in all_results)
    total_stt = sum(r["stt_count"] for r in all_results)
    total_ocr = sum(r["ocr_count"] for r in all_results)
    print(f"{'─' * 35} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6}")
    print(f"{'합계':<35} {total_yolo:>6} {total_clip:>6} {total_stt:>6} {total_ocr:>6}")

    # ── 결과 텍스트 파일 저장 ──
    out_dir = PROJECT_ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    report_path = out_dir / "multimodal_test_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  YOLO + CLIP + STT 멀티모달 통합 테스트 결과\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"{'VOD':<40} {'YOLO':>6} {'CLIP':>6} {'STT':>6}\n")
        f.write(f"{'─' * 40} {'─' * 6} {'─' * 6} {'─' * 6}\n")
        for r in all_results:
            name = r["filename"][:38]
            f.write(f"{name:<40} {r['yolo_count']:>6} {r['clip_count']:>6} {r['stt_count']:>6}\n")
        f.write(f"{'─' * 40} {'─' * 6} {'─' * 6} {'─' * 6}\n")
        f.write(f"{'합계':<40} {total_yolo:>6} {total_clip:>6} {total_stt:>6}\n")

    print(f"\n결과 저장: {report_path}")
    print("\n완료!")


if __name__ == "__main__":
    main()
