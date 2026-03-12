"""
TV 연예/오락 에피소드별 CLIP 배치 임베딩 (박아름)

기존 batch_embed.py의 문제:
  - crawl_status.json (구버전, 시리즈 공유) 읽음
  - 같은 파일 공유하는 vod_id 전체에 동일 벡터 복사
  - data/trailers/ 기본 경로 사용

개선:
  - crawl_status_아름.json 읽음 (에피소드별 개별 수집 결과)
  - data/trailers_아름/ 경로 사용
  - 각 vod_id 개별 임베딩 (파일이 달라야 벡터가 달라짐)
  - 상태 파일: embed_status_아름.json
  - 출력: embeddings_아름_v2.parquet

실행:
    cd VOD_Embedding
    python scripts/batch_embed_아름.py
    python scripts/batch_embed_아름.py --status
    python scripts/batch_embed_아름.py --dry-run --limit 10
    python scripts/batch_embed_아름.py --out-file data/embeddings_아름_v2.parquet
"""

import sys
import os
import json
import argparse
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT  = Path(__file__).parent.parent
DATA_DIR      = PROJECT_ROOT / "data"
TRAILERS_DIR  = DATA_DIR / "trailers_아름"
CRAWL_STATUS  = DATA_DIR / "crawl_status_아름.json"
EMBED_STATUS  = DATA_DIR / "embed_status_아름.json"
DEFAULT_OUT   = DATA_DIR / "embeddings_아름_v2.parquet"

BATCH_SAVE_INTERVAL = 50
N_FRAMES      = 10
MODEL_PATH    = "C:/Users/daewo/DX_prod_2nd/my_clip_model"
MODEL_FALLBACK = "clip-ViT-B-32"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "embed_아름.log", encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 모델 로드
# ---------------------------------------------------------------------------

def load_clip_model():
    from sentence_transformers import SentenceTransformer
    model_dir = Path(MODEL_PATH)
    if model_dir.exists():
        log.info(f"로컬 모델 로드: {MODEL_PATH}")
        return SentenceTransformer(str(model_dir))
    log.info(f"HuggingFace에서 모델 다운로드: {MODEL_FALLBACK}")
    return SentenceTransformer(MODEL_FALLBACK)


# ---------------------------------------------------------------------------
# 프레임 추출 + 임베딩
# ---------------------------------------------------------------------------

def extract_frames(video_path: str) -> list:
    import cv2
    from PIL import Image

    cap   = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps   = cap.get(cv2.CAP_PROP_FPS)

    if total <= 0 or fps <= 0:
        cap.release()
        raise ValueError(f"유효하지 않은 영상: {video_path}")

    indices = np.linspace(0, total - 1, N_FRAMES, dtype=int)
    frames  = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret:
            frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()

    if not frames:
        raise ValueError("프레임을 하나도 추출하지 못함")
    return frames


def get_video_embedding(video_path: str, model) -> np.ndarray:
    frames  = extract_frames(video_path)
    vectors = model.encode(frames, convert_to_numpy=True, show_progress_bar=False)
    return vectors.mean(axis=0).astype(np.float32)


def check_vector_quality(vec: np.ndarray) -> bool:
    mag = float(np.linalg.norm(vec))
    return 0.01 <= mag <= 100.0


# ---------------------------------------------------------------------------
# 상태 파일
# ---------------------------------------------------------------------------

def load_embed_status() -> dict:
    if EMBED_STATUS.exists():
        with open(EMBED_STATUS, encoding='utf-8') as f:
            return json.load(f)
    return {
        "last_updated": None,
        "total": 0,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "done_vod_ids": [],
    }


def save_embed_status(status: dict):
    status["last_updated"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(EMBED_STATUS, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def print_status(status: dict):
    total     = status.get("total", 0)
    processed = status.get("processed", 0)
    pct = f"{processed/total*100:.1f}%" if total > 0 else "0%"
    print(f"\n=== CLIP 임베딩 진행 현황 (박아름 v2 — 에피소드별) ===")
    print(f"  전체 대상: {total:,}개")
    print(f"  처리 완료: {processed:,}개 ({pct})")
    print(f"  성공:      {status.get('success', 0):,}개")
    print(f"  실패:      {status.get('failed', 0):,}개")
    print(f"  마지막 갱신: {status.get('last_updated', 'N/A')}")
    print()


# ---------------------------------------------------------------------------
# 작업 목록 구성
# ---------------------------------------------------------------------------

def load_crawl_status() -> dict:
    """crawl_trailers_아름.py 결과 읽기"""
    if not CRAWL_STATUS.exists():
        log.error(f"crawl_status_아름.json 없음: {CRAWL_STATUS}")
        log.error("crawl_trailers_아름.py 를 먼저 실행하세요.")
        sys.exit(1)
    with open(CRAWL_STATUS, encoding='utf-8') as f:
        data = json.load(f)
    return data.get("vods", {})


def build_work_list(crawl_vods: dict, done_ids: set) -> list:
    """
    에피소드별 개별 작업 목록 구성.
    각 vod_id가 자신의 파일을 갖는지 확인.
    같은 파일을 공유해도 vod_id별로 개별 처리 (fallback 케이스).
    """
    work = []
    for vod_id, info in crawl_vods.items():
        if info.get("status") != "success":
            continue
        if vod_id in done_ids:
            continue
        filename = info.get("filename", "")
        filepath = TRAILERS_DIR / filename
        if not filepath.exists():
            log.warning(f"파일 없음 스킵: {filename} ({vod_id})")
            continue
        work.append({
            "vod_id":       vod_id,
            "filename":     filename,
            "filepath":     str(filepath),
            "asset_nm":     info.get("asset_nm", vod_id),
            "series_nm":    info.get("series_nm"),
            "release_date": info.get("release_date"),
            "query_used":   info.get("query_used", ""),
        })
    return work


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="TV 연예/오락 에피소드별 CLIP 임베딩 (박아름)")
    parser.add_argument('--status', action='store_true', help='진행 상황만 출력')
    parser.add_argument('--dry-run', action='store_true', help='실제 임베딩 없이 작업 목록 확인')
    parser.add_argument('--limit', type=int, default=0, help='처리 건수 제한 (테스트용)')
    parser.add_argument('--out-file', type=str, default=str(DEFAULT_OUT),
                        help=f'출력 parquet 경로 (기본: {DEFAULT_OUT})')
    parser.add_argument('--delete-after-embed', action='store_true',
                        help='임베딩 완료 후 영상 파일 삭제 (디스크 절약)')
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = load_embed_status()

    if args.status:
        print_status(status)
        return

    # 완료된 vod_id
    done_ids = set(status.get("done_vod_ids", []))

    # 크롤링 결과 로드
    crawl_vods = load_crawl_status()
    work_list  = build_work_list(crawl_vods, done_ids)

    if args.limit > 0:
        work_list = work_list[:args.limit]

    status["total"] = len(crawl_vods)
    log.info(f"임베딩 대상: {len(work_list):,}건 (완료: {len(done_ids):,}건 스킵)")

    if not work_list:
        log.info("처리할 새 항목 없음")
        print_status(status)
        return

    if args.dry_run:
        log.info("[DRY-RUN] 첫 10건 쿼리 확인:")
        for item in work_list[:10]:
            log.info(f"  {item['asset_nm']} → {item['filename']} (쿼리: {item['query_used']})")
        return

    # 모델 로드
    log.info("CLIP 모델 로드 중...")
    model = load_clip_model()
    log.info("모델 로드 완료")

    import pandas as pd
    results = []
    out_path = Path(args.out_file)

    # 기존 parquet 이어받기
    if out_path.exists() and done_ids:
        existing_df = pd.read_parquet(out_path)
        results = existing_df.to_dict("records")
        log.info(f"기존 parquet 로드: {len(results):,}건")

    for i, item in enumerate(work_list):
        vod_id   = item["vod_id"]
        filepath = item["filepath"]

        try:
            vec = get_video_embedding(filepath, model)
            if not check_vector_quality(vec):
                raise ValueError(f"이상 벡터 (magnitude={float(np.linalg.norm(vec)):.4f})")

            results.append({
                "vod_id":    vod_id,
                "embedding": vec.tolist(),
                "filename":  item["filename"],
                "asset_nm":  item["asset_nm"],
                "query_used": item["query_used"],
            })
            done_ids.add(vod_id)
            status["success"] = status.get("success", 0) + 1
            log.info(f"[{i+1}/{len(work_list)}] OK  {item['asset_nm']} → {item['filename']}")

            if args.delete_after_embed:
                p = Path(filepath)
                if p.exists():
                    size_mb = p.stat().st_size / 1024 / 1024
                    p.unlink()
                    log.info(f"  영상 삭제: {p.name} ({size_mb:.1f}MB)")

        except Exception as e:
            status["failed"] = status.get("failed", 0) + 1
            log.warning(f"[{i+1}/{len(work_list)}] FAIL {item['asset_nm']}: {e}")

        status["processed"] = status.get("processed", 0) + 1

        # 체크포인트 저장
        if (i + 1) % BATCH_SAVE_INTERVAL == 0:
            status["done_vod_ids"] = list(done_ids)
            pd.DataFrame(results).to_parquet(out_path, index=False)
            save_embed_status(status)
            log.info(f"체크포인트 저장 — {i+1}/{len(work_list)}건")

    # 최종 저장
    status["done_vod_ids"] = list(done_ids)
    df = pd.DataFrame(results)
    df.to_parquet(out_path, index=False)
    save_embed_status(status)
    log.info(f"저장 완료: {out_path} ({len(df):,}건, {out_path.stat().st_size/1024/1024:.1f}MB)")
    print_status(status)


if __name__ == "__main__":
    main()
