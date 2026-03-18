"""
batch_detect.py — VOD 배치 사물인식 실행 스크립트

실행:
    cd Object_Detection
    python scripts/batch_detect.py --input-dir data/trailers_아름 --limit 10 --random
    python scripts/batch_detect.py --status
    python scripts/batch_detect.py --dry-run --limit 5
"""
import sys
import os
import json
import random
import logging
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from frame_extractor import extract_frames, list_video_files
from detector import Detector
from vod_filter import filter_videos_by_ct_cl

DATA_DIR    = PROJECT_ROOT / "data"
STATUS_FILE = DATA_DIR / "detect_status.json"
LOG_FILE    = DATA_DIR / "detect.log"

DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)


# ─────────────────────────────────────────
# 상태 파일
# ─────────────────────────────────────────

def load_status() -> dict:
    if STATUS_FILE.exists():
        with open(STATUS_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"last_updated": None, "total": 0, "processed": 0, "success": 0, "failed": 0, "vods": {}}


def save_status(status: dict):
    status["last_updated"] = datetime.now().isoformat()
    vods = status["vods"]
    status["processed"] = sum(1 for v in vods.values() if v.get("status") in ("success", "failed"))
    status["success"]   = sum(1 for v in vods.values() if v.get("status") == "success")
    status["failed"]    = sum(1 for v in vods.values() if v.get("status") == "failed")
    with open(STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def print_status(status: dict):
    total = status.get("total", 0)
    pct   = f"{status['processed']/total*100:.1f}%" if total > 0 else "0%"
    print(f"\n=== Object Detection 진행 현황 ===")
    print(f"  전체 대상: {total:,}건")
    print(f"  처리 완료: {status['processed']:,}건 ({pct})")
    print(f"  성공:      {status['success']:,}건")
    print(f"  실패:      {status['failed']:,}건")
    print(f"  마지막 갱신: {status.get('last_updated', 'N/A')}\n")


# ─────────────────────────────────────────
# parquet 저장
# ─────────────────────────────────────────

def append_parquet(records: list, out_path: Path):
    df_new = pd.DataFrame(records)
    if out_path.exists():
        df_old = pd.read_parquet(str(out_path))
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_parquet(str(out_path), index=False)


# ─────────────────────────────────────────
# 메인
# ─────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="VOD 배치 사물인식 (Object_Detection)")
    parser.add_argument("--input-dir", type=str, default=str(PROJECT_ROOT / "data" / "trailers_아름"),
                        help="VOD 영상 파일 디렉터리")
    parser.add_argument("--output",    type=str, default=str(DATA_DIR / "vod_detected_object.parquet"))
    parser.add_argument("--model",     type=str, default="yolo11s.pt",
                        help="yolo11n.pt | yolo11s.pt | yolov8s.pt 등")
    parser.add_argument("--fps",       type=float, default=1.0)
    parser.add_argument("--conf",      type=float, default=0.5)
    parser.add_argument("--device",    type=str, default="cpu")
    parser.add_argument("--limit",     type=int, default=0, help="처리 파일 수 제한")
    parser.add_argument("--random",    action="store_true", help="랜덤 샘플링 (--limit과 함께 사용)")
    parser.add_argument("--dry-run",   action="store_true", help="파일 목록만 출력, 추론 X")
    parser.add_argument("--status",    action="store_true", help="진행 상황 출력")
    parser.add_argument("--batch-save-interval", type=int, default=10)
    parser.add_argument("--ct-cl", type=str, default="TV 연예/오락",
                        help="처리 대상 콘텐츠 분류 (기본값: 'TV 연예/오락', 전체는 '')")
    args = parser.parse_args()

    status = load_status()

    if args.status:
        print_status(status)
        return

    # 영상 파일 목록
    video_files = list_video_files(args.input_dir)
    if not video_files:
        log.error(f"영상 파일 없음: {args.input_dir}")
        return

    # ct_cl 필터
    if args.ct_cl:
        video_files = filter_videos_by_ct_cl(video_files, args.ct_cl)
        if not video_files:
            log.error(f"ct_cl='{args.ct_cl}' 조건에 맞는 영상 없음")
            return

    # 랜덤 샘플링
    if args.random and args.limit > 0:
        video_files = random.sample(video_files, min(args.limit, len(video_files)))
        log.info(f"랜덤 {len(video_files)}건 선택")
    elif args.limit > 0:
        video_files = video_files[:args.limit]

    status["total"] = len(video_files)
    log.info(f"대상: {len(video_files)}건 | 모델: {args.model} | fps: {args.fps} | conf: {args.conf}")

    if args.dry_run:
        for f in video_files:
            log.info(f"[DRY-RUN] {f.name}")
        return

    # Detector 초기화
    det = Detector(model_name=args.model, confidence=args.conf, device=args.device)

    run_success = run_failed = 0
    buffer = []

    for i, video_path in enumerate(video_files):
        vod_id = video_path.stem  # 파일명(확장자 제외)을 vod_id로 사용

        # 이미 처리된 파일 스킵
        if vod_id in status["vods"] and status["vods"][vod_id].get("status") == "success":
            log.info(f"[스킵] {video_path.name}")
            continue

        try:
            frames, timestamps = extract_frames(str(video_path), fps=args.fps)
            results = det.infer(frames, timestamps)
            records = det.to_records(vod_id, results)

            buffer.extend(records)
            status["vods"][vod_id] = {
                "status":       "success",
                "file":         video_path.name,
                "frame_count":  len(frames),
                "detect_count": len(records),
                "processed_at": datetime.now().isoformat(),
            }
            run_success += 1
            log.info(f"[{run_success+run_failed}/{len(video_files)}] OK {video_path.name} "
                     f"— 프레임 {len(frames)}개, 탐지 {len(records)}건")

        except Exception as e:
            status["vods"][vod_id] = {"status": "failed", "file": video_path.name, "error": str(e)}
            run_failed += 1
            log.warning(f"[{run_success+run_failed}/{len(video_files)}] FAIL {video_path.name}: {e}")

        # 배치 저장
        if buffer and (i + 1) % args.batch_save_interval == 0:
            append_parquet(buffer, Path(args.output))
            buffer.clear()
            save_status(status)

    # 마지막 저장
    if buffer:
        append_parquet(buffer, Path(args.output))
    save_status(status)

    log.info(f"=== 완료 === 성공: {run_success} / 실패: {run_failed} / 대상: {len(video_files)}")
    log.info(f"결과 저장: {args.output}")

    # 간단한 인식률 요약 출력
    if Path(args.output).exists():
        df = pd.read_parquet(args.output)
        log.info(f"\n--- 탐지 결과 요약 ---")
        log.info(f"총 탐지 건수: {len(df):,}")
        log.info(f"고유 라벨 수: {df['label'].nunique()}")
        log.info(f"상위 10개 라벨:\n{df['label'].value_counts().head(10).to_string()}")


if __name__ == "__main__":
    main()
