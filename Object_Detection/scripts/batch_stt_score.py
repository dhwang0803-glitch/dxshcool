"""
batch_stt_score.py — VOD STT 배치 스코어링

실행:
    cd Object_Detection
    python scripts/batch_stt_score.py --input-dir ../VOD_Embedding/data/trailers_아름 --limit 5
    python scripts/batch_stt_score.py --status
    python scripts/batch_stt_score.py --dry-run --limit 3
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

from frame_extractor import list_video_files
from audio_extractor import AudioExtractor
from vod_filter import filter_videos_by_ct_cl
from stt_scorer import SttScorer
from keyword_mapper import KeywordMapper
from location_tagger import LocationTagger

DATA_DIR    = PROJECT_ROOT / "data"
CONFIG_PATH = PROJECT_ROOT / "config" / "stt_keywords.yaml"
STATUS_FILE = DATA_DIR / "stt_status.json"
LOG_FILE    = DATA_DIR / "stt_score.log"

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
    print(f"\n=== STT 스코어링 진행 현황 ===")
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
    parser = argparse.ArgumentParser(description="VOD STT 배치 스코어링")
    parser.add_argument("--input-dir", type=str, default=str(PROJECT_ROOT / "data" / "trailers_아름"))
    parser.add_argument("--output",    type=str, default=str(DATA_DIR / "vod_stt_concept.parquet"))
    parser.add_argument("--config",    type=str, default=str(CONFIG_PATH))
    parser.add_argument("--model",     type=str, default="small", help="Whisper 모델 (tiny/base/small/medium)")
    parser.add_argument("--limit",     type=int, default=0)
    parser.add_argument("--random",    action="store_true")
    parser.add_argument("--dry-run",   action="store_true")
    parser.add_argument("--status",    action="store_true")
    parser.add_argument("--batch-save-interval", type=int, default=10)
    parser.add_argument("--random-location", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--ct-cl", type=str, default="TV 연예/오락",
                        help="처리 대상 콘텐츠 분류 (기본값: 'TV 연예/오락', 전체는 '')")
    args = parser.parse_args()

    status = load_status()
    if args.status:
        print_status(status)
        return

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

    if args.random and args.limit > 0:
        video_files = random.sample(video_files, min(args.limit, len(video_files)))
        log.info(f"랜덤 {len(video_files)}건 선택")
    elif args.limit > 0:
        video_files = video_files[:args.limit]

    status["total"] = len(video_files)
    log.info(f"대상: {len(video_files)}건 | Whisper 모델: {args.model}")

    if args.dry_run:
        for f in video_files:
            log.info(f"[DRY-RUN] {f.name}")
        return

    audio_ext    = AudioExtractor()
    stt_scorer   = SttScorer(model_name=args.model)
    kw_mapper    = KeywordMapper(args.config)
    loc_tagger   = LocationTagger()

    run_success = run_failed = 0
    buffer = []

    for i, video_path in enumerate(video_files):
        vod_id = video_path.stem

        if vod_id in status["vods"] and status["vods"][vod_id].get("status") == "success":
            log.info(f"[스킵] {video_path.name}")
            continue

        wav_path = None
        try:
            # 오디오 추출
            wav_path = audio_ext.extract(str(video_path))

            # STT
            segments = stt_scorer.transcribe(wav_path)

            # 키워드 매핑
            records = []
            for seg in segments:
                matched = kw_mapper.match(
                    transcript=seg["text"],
                    vod_id=vod_id,
                    start_ts=seg["start"],
                    end_ts=seg["end"],
                )
                records.extend(matched)

            # 위치 시뮬레이션
            if args.random_location and records:
                lat, lng  = loc_tagger.random_location()
                loc_tag   = loc_tagger.tag(lat, lng)
                for r in records:
                    r["region"]  = loc_tag["region"]
                    r["sim_lat"] = lat
                    r["sim_lng"] = lng

            buffer.extend(records)
            status["vods"][vod_id] = {
                "status":       "success",
                "file":         video_path.name,
                "segments":     len(segments),
                "stt_records":  len(records),
                "processed_at": datetime.now().isoformat(),
            }
            run_success += 1
            log.info(f"[{run_success+run_failed}/{len(video_files)}] OK {video_path.name} "
                     f"— 구간 {len(segments)}개, 키워드 {len(records)}건")

        except Exception as e:
            status["vods"][vod_id] = {"status": "failed", "file": video_path.name, "error": str(e)}
            run_failed += 1
            log.warning(f"[{run_success+run_failed}/{len(video_files)}] FAIL {video_path.name}: {e}")

        finally:
            # 임시 WAV 파일 정리
            if wav_path and Path(wav_path).exists():
                Path(wav_path).unlink(missing_ok=True)

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
        log.info(f"\n--- STT 스코어링 요약 ---")
        log.info(f"총 키워드 매칭 건수: {len(df):,}")
        if len(df) > 0:
            log.info(f"상위 키워드:\n{df['keyword'].value_counts().head(10).to_string()}")
            log.info(f"카테고리 분포:\n{df['ad_category'].value_counts().to_string()}")


if __name__ == "__main__":
    main()
