"""
batch_ocr_score.py — VOD OCR 배치 스코어링

프레임 자막에서 텍스트 추출 → keyword_mapper 매칭 → parquet 저장.
DB detected_object_ocr 스키마 매칭 (frame_ts, detected_text, confidence, bbox).

실행:
    cd Object_Detection
    python scripts/batch_ocr_score.py --input-dir data/trailers --limit 5
    python scripts/batch_ocr_score.py --status
    python scripts/batch_ocr_score.py --dry-run --limit 3
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
from ocr_scorer import OcrScorer
from keyword_mapper import KeywordMapper
from vod_filter import filter_videos_by_ct_cl

DATA_DIR    = PROJECT_ROOT / "data"
CONFIG_PATH = PROJECT_ROOT / "config" / "stt_keywords.yaml"
STATUS_FILE = DATA_DIR / "ocr_status.json"
LOG_FILE    = DATA_DIR / "ocr_score.log"

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
    print(f"\n=== OCR 스코어링 진행 현황 ===")
    print(f"  전체 대상: {total:,}건")
    print(f"  처리 완료: {status['processed']:,}건 ({pct})")
    print(f"  성공:      {status['success']:,}건")
    print(f"  실패:      {status['failed']:,}건")
    print(f"  마지막 갱신: {status.get('last_updated', 'N/A')}\n")


def append_parquet(records: list, out_path: Path):
    df_new = pd.DataFrame(records)
    if out_path.exists():
        df_old = pd.read_parquet(str(out_path))
        df = pd.concat([df_old, df_new], ignore_index=True)
    else:
        df = df_new
    df.to_parquet(str(out_path), index=False)


def main():
    parser = argparse.ArgumentParser(description="VOD OCR 배치 스코어링")
    parser.add_argument("--input-dir", type=str, default=str(PROJECT_ROOT / "data" / "trailers_아름"))
    parser.add_argument("--output",    type=str, default=str(DATA_DIR / "vod_ocr_concept.parquet"))
    parser.add_argument("--config",    type=str, default=str(CONFIG_PATH))
    parser.add_argument("--fps",       type=float, default=1.0)
    parser.add_argument("--ocr-interval", type=int, default=3,
                        help="N프레임마다 OCR (기본 3 = 3초에 1번)")
    parser.add_argument("--limit",     type=int, default=0)
    parser.add_argument("--random",    action="store_true")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--status",    action="store_true")
    parser.add_argument("--batch-save-interval", type=int, default=5)
    parser.add_argument("--ct-cl", type=str, default="TV 연예/오락")
    args = parser.parse_args()

    status = load_status()
    if args.status:
        print_status(status)
        return

    video_files = list_video_files(args.input_dir)
    if not video_files:
        log.error(f"영상 파일 없음: {args.input_dir}")
        return

    if args.ct_cl:
        video_files = filter_videos_by_ct_cl(video_files, args.ct_cl)
        if not video_files:
            log.error(f"ct_cl='{args.ct_cl}' 조건에 맞는 영상 없음")
            return

    if args.random and args.limit > 0:
        video_files = random.sample(video_files, min(args.limit, len(video_files)))
    elif args.limit > 0:
        video_files = video_files[:args.limit]

    status["total"] = len(video_files)
    log.info(f"대상: {len(video_files)}건 | OCR 간격: {args.ocr_interval}프레임")

    if args.dry_run:
        for f in video_files:
            log.info(f"[DRY-RUN] {f.name}")
        return

    ocr = OcrScorer(["ko", "en"])
    kw_mapper = KeywordMapper(args.config)

    run_success = run_failed = 0
    buffer = []

    for i, video_path in enumerate(video_files):
        vod_id = video_path.stem

        if vod_id in status["vods"] and status["vods"][vod_id].get("status") == "success":
            log.info(f"[스킵] {video_path.name}")
            continue

        try:
            frames, timestamps = extract_frames(str(video_path), fps=args.fps)
            if not frames:
                raise ValueError("프레임 0개")

            # OCR 상세 추출 (bbox + confidence)
            ocr_details = ocr.extract_details(frames, timestamps, sample_interval=args.ocr_interval)

            # 키워드 매칭 + DB 스키마 매칭
            records = []
            for d in ocr_details:
                # keyword_mapper로 ad_category/region 매칭
                kw_matches = kw_mapper.match(
                    d["text"], vod_id,
                    d["frame_ts"], d["frame_ts"] + 1.0
                )
                # 매칭된 키워드에서 ad_category, region_hint 추출
                ad_category = None
                region_hint = None
                for m in kw_matches:
                    if len(m["keyword"]) >= 2:  # 2글자 이상만
                        ad_category = m["ad_category"]
                        if m["ad_category"] == "관광지":
                            region_hint = m["keyword"]

                records.append({
                    "vod_id":        vod_id,
                    "frame_ts":      d["frame_ts"],
                    "detected_text": d["text"],
                    "confidence":    d["confidence"],
                    "bbox":          d["bbox"],
                    "ad_category":   ad_category,
                    "region_hint":   region_hint,
                })

            buffer.extend(records)
            status["vods"][vod_id] = {
                "status":       "success",
                "file":         video_path.name,
                "frame_count":  len(frames),
                "ocr_texts":    len(ocr_details),
                "ocr_records":  len(records),
                "processed_at": datetime.now().isoformat(),
            }
            run_success += 1
            log.info(f"[{run_success+run_failed}/{len(video_files)}] OK {video_path.name} "
                     f"— 프레임 {len(frames)}개, OCR {len(ocr_details)}건, 레코드 {len(records)}건")

        except Exception as e:
            status["vods"][vod_id] = {"status": "failed", "file": video_path.name, "error": str(e)}
            run_failed += 1
            log.warning(f"[{run_success+run_failed}/{len(video_files)}] FAIL {video_path.name}: {e}")

        if buffer and (i + 1) % args.batch_save_interval == 0:
            append_parquet(buffer, Path(args.output))
            buffer.clear()
            save_status(status)

    if buffer:
        append_parquet(buffer, Path(args.output))
    save_status(status)

    log.info(f"=== 완료 === 성공: {run_success} / 실패: {run_failed} / 대상: {len(video_files)}")
    log.info(f"결과 저장: {args.output}")

    if Path(args.output).exists():
        df = pd.read_parquet(args.output)
        log.info(f"\n--- OCR 스코어링 요약 ---")
        log.info(f"총 OCR 레코드: {len(df):,}")
        if "ad_category" in df.columns:
            matched = df[df["ad_category"].notna()]
            log.info(f"키워드 매칭: {len(matched):,}건")
            if len(matched) > 0:
                log.info(f"카테고리 분포:\n{matched['ad_category'].value_counts().to_string()}")


if __name__ == "__main__":
    main()
