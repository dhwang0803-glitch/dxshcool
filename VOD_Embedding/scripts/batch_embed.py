"""
PLAN_02: CLIP 배치 임베딩
trailers/*.webm → CLIP ViT-B/32 → data/video_embs_batch_*.pkl (기본)
                                 → embeddings_output.parquet   (팀원 협업용)

실행:
    conda activate myenv
    python pipeline/batch_embed.py                          # pkl 모드 (DB 직접 적재용)
    python pipeline/batch_embed.py --start-batch 3
    python pipeline/batch_embed.py --status
    python pipeline/batch_embed.py --output parquet         # 팀원 제출용
    python pipeline/batch_embed.py --output parquet --out-file embeddings_홍길동.parquet
"""

import sys
import os
import json
import pickle
import argparse
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT         = Path(__file__).parent.parent
DATA_DIR             = PROJECT_ROOT / "data"
DEFAULT_TRAILERS_DIR = Path("C:/Users/daewo/DX_prod_2nd/trailers")
STATUS_FILE          = DATA_DIR / "embed_status.json"   # --embed-status-file 인자로 덮어씀
CRAWL_STATUS_FILE    = DATA_DIR / "crawl_status.json"   # --crawl-status-file 인자로 덮어씀

BATCH_SIZE    = 100
N_FRAMES      = 10
MODEL_PATH    = "C:/Users/daewo/DX_prod_2nd/my_clip_model"
MODEL_FALLBACK = "clip-ViT-B-32"   # HuggingFace Hub fallback

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(DATA_DIR / "embed.log", encoding='utf-8'),
    ]
)
log = logging.getLogger(__name__)


def load_clip_model():
    from sentence_transformers import SentenceTransformer
    model_dir = Path(MODEL_PATH)
    if model_dir.exists():
        log.info(f"로컬 모델 로드: {MODEL_PATH}")
        return SentenceTransformer(str(model_dir))
    else:
        log.info(f"HuggingFace에서 모델 다운로드: {MODEL_FALLBACK}")
        return SentenceTransformer(MODEL_FALLBACK)


def extract_frames(video_path: str) -> list:
    """영상에서 N_FRAMES개 균등 추출 → PIL.Image 리스트"""
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
    """영상 → 512차원 float32 벡터"""
    frames  = extract_frames(video_path)
    vectors = model.encode(frames, convert_to_numpy=True, show_progress_bar=False)
    mean_vec = vectors.mean(axis=0).astype(np.float32)
    return mean_vec


def check_vector_quality(vec: np.ndarray) -> bool:
    mag = float(np.linalg.norm(vec))
    return 0.01 <= mag <= 100.0


def load_status(status_file: Path) -> dict:
    if status_file.exists():
        with open(status_file, encoding='utf-8') as f:
            return json.load(f)
    return {
        "last_updated": None,
        "total_trailers": 0,
        "processed": 0,
        "success": 0,
        "failed": 0,
        "batches_completed": [],
        "failed_vods": {}
    }


def save_status(status: dict, status_file: Path):
    status["last_updated"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(status_file, 'w', encoding='utf-8') as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def load_crawl_status(crawl_status_file: Path) -> dict:
    """PLAN_01 결과 읽기 (vod_id → filename 매핑)"""
    if crawl_status_file.exists():
        with open(crawl_status_file, encoding='utf-8') as f:
            data = json.load(f)
        return data.get("vods", {})
    return {}


def build_work_list(crawl_vods: dict, done_vod_ids: set, trailers_dir: Path) -> list:
    """
    성공적으로 다운로드된 트레일러 목록 반환.
    이미 임베딩 완료된 vod_id는 제외.
    ct_cl, series_nm은 crawl_status에서 전달 (ingest --propagate 시 시리즈 전파에 사용).
    """
    work = []
    for vod_id, info in crawl_vods.items():
        if info.get("status") != "success":
            continue
        if vod_id in done_vod_ids:
            continue
        filename = info.get("filename", "")
        filepath = trailers_dir / filename
        if filepath.exists():
            work.append({
                "vod_id":    vod_id,
                "filename":  filename,
                "filepath":  str(filepath),
                "title":     info.get("title", vod_id),
                "ct_cl":     info.get("ct_cl"),
                "series_nm": info.get("series_nm"),
            })
    return work


def save_batch(batch_data: list, batch_num: int) -> str:
    filename = f"video_embs_batch_{batch_num:03d}.pkl"
    filepath = DATA_DIR / filename
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(filepath, 'wb') as f:
        pickle.dump(batch_data, f)
    log.info(f"배치 저장: {filename} ({len(batch_data)}건)")
    return filename


def save_parquet(results: list, out_file: str):
    """임베딩 결과를 parquet으로 저장 (팀원 제출용).

    출력 컬럼:
        vod_id    (str)          — DB vod_id_fk 와 동일
        embedding (list[float32]) — 512차원 벡터
    """
    import pandas as pd

    rows = [{"vod_id": r["vod_id"], "embedding": r["vector"].tolist()} for r in results]
    df = pd.DataFrame(rows)

    # 검증
    assert df["embedding"].apply(len).eq(512).all(), "512차원 아닌 행 존재"
    assert df["vod_id"].is_unique, "vod_id 중복 존재"

    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    log.info(f"parquet 저장 완료: {out_path} ({len(df):,}건)")


def already_embedded_vod_ids(status: dict) -> set:
    """완료된 배치 pkl에서 vod_id 목록 복원"""
    done_ids = set()
    for batch_file in status.get("batches_completed", []):
        pkl_path = DATA_DIR / batch_file
        if pkl_path.exists():
            with open(pkl_path, 'rb') as f:
                batch = pickle.load(f)
            for item in batch:
                done_ids.add(item["vod_id"])
    return done_ids


def print_status(status: dict):
    total     = status.get("total_trailers", 0)
    processed = status.get("processed", 0)
    pct = f"{processed/total*100:.1f}%" if total > 0 else "0%"

    print(f"\n=== 임베딩 진행 현황 ===")
    print(f"  전체 트레일러: {total:,}개")
    print(f"  처리 완료:     {processed:,}개 ({pct})")
    print(f"  성공:          {status.get('success', 0):,}개")
    print(f"  실패:          {status.get('failed', 0):,}개")
    print(f"  완료 배치:     {len(status.get('batches_completed', []))}개")
    print(f"  마지막 갱신:   {status.get('last_updated', 'N/A')}")
    print()


def delete_video_file(filepath: str):
    """임베딩 완료된 영상 파일 삭제"""
    p = Path(filepath)
    if p.exists():
        size_mb = p.stat().st_size / (1024 * 1024)
        p.unlink()
        log.info(f"영상 삭제: {p.name} ({size_mb:.1f}MB 회수)")


def main():
    parser = argparse.ArgumentParser(description="CLIP 배치 임베딩")
    parser.add_argument('--start-batch', type=int, default=1, help='시작 배치 번호')
    parser.add_argument('--end-batch',   type=int, default=0, help='종료 배치 번호 (0=전체)')
    parser.add_argument('--status', action='store_true', help='진행 상황만 출력')
    parser.add_argument('--delete-after-embed', action='store_true',
                        help='임베딩 완료 후 영상 파일 즉시 삭제 (디스크 절약)')
    parser.add_argument('--trailers-dir', type=str, default=str(DEFAULT_TRAILERS_DIR),
                        help=f'트레일러 경로 (기본: {DEFAULT_TRAILERS_DIR})')
    parser.add_argument('--output', choices=['pkl', 'parquet'], default='pkl',
                        help='출력 포맷: pkl(기본, DB 적재용) / parquet(팀원 제출용)')
    parser.add_argument('--out-file', type=str, default='',
                        help='parquet 출력 파일명 (기본: data/embeddings_output.parquet)')
    parser.add_argument('--crawl-status-file', type=str, default='',
                        help='크롤 상태 파일 경로 (기본: data/crawl_status.json). 병렬 실행 시 파티션별 지정')
    parser.add_argument('--embed-status-file', type=str, default='',
                        help='임베딩 상태 파일 경로 (기본: data/embed_status.json). 병렬 실행 시 파티션별 지정')
    args = parser.parse_args()
    CRAWL_STATUS_FILE = Path(args.crawl_status_file) if args.crawl_status_file else DATA_DIR / "crawl_status.json"
    STATUS_FILE       = Path(args.embed_status_file)  if args.embed_status_file  else DATA_DIR / "embed_status.json"
    TRAILERS_DIR = Path(args.trailers_dir)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    status = load_status(STATUS_FILE)

    if args.status:
        print_status(status)
        return

    # 이미 처리된 vod_id 복원
    done_ids = already_embedded_vod_ids(status)

    # PLAN_01 결과 로드
    crawl_vods = load_crawl_status(CRAWL_STATUS_FILE)
    if not crawl_vods:
        # PLAN_01 미완료 시 trailers/ 폴더에서 직접 스캔
        log.warning("crawl_status.json 없음 — trailers/ 폴더 직접 스캔")
        crawl_vods = {}
        for f in TRAILERS_DIR.glob("*.webm"):
            vod_id = f.stem   # filename without extension
            crawl_vods[vod_id] = {
                "status": "success",
                "filename": f.name,
                "title": f.stem,
            }

    work_list = build_work_list(crawl_vods, done_ids, TRAILERS_DIR)
    status["total_trailers"] = len(crawl_vods)
    log.info(f"임베딩 대상: {len(work_list):,}개")

    if not work_list:
        log.info("처리할 새 항목 없음")
        print_status(status)
        return

    # 모델 로드
    log.info("CLIP 모델 로드 중...")
    model = load_clip_model()
    log.info("모델 로드 완료")

    use_parquet = (args.output == 'parquet')
    parquet_results = [] if use_parquet else None

    # pkl 모드: 배치 번호 계산 및 이어서 처리
    completed_batches = len(status.get("batches_completed", []))
    batch_num   = max(args.start_batch, completed_batches + 1)
    batch_data  = []

    for i, item in enumerate(work_list):
        # end-batch 제한 (pkl 모드 전용)
        if not use_parquet and args.end_batch > 0 and batch_num > args.end_batch:
            log.info(f"--end-batch {args.end_batch} 도달, 중단")
            break

        vod_id    = item["vod_id"]
        filepath  = item["filepath"]

        embed_ok = False
        try:
            vec = get_video_embedding(filepath, model)
            if not check_vector_quality(vec):
                raise ValueError(f"이상 벡터 (magnitude={float(np.linalg.norm(vec)):.4f})")

            record = {
                "vod_id":       vod_id,
                "title":        item["title"],
                "video_file":   item["filename"],
                "vector":       vec,
                "magnitude":    float(np.linalg.norm(vec)),
                "embedded_at":  datetime.now().isoformat(),
                "ct_cl":        item.get("ct_cl"),
                "series_nm":    item.get("series_nm"),
            }
            if use_parquet:
                parquet_results.append(record)
            else:
                batch_data.append(record)

            status["success"] = status.get("success", 0) + 1
            log.info(f"[{i+1}/{len(work_list)}] OK  {vod_id}")
            embed_ok = True

        except Exception as e:
            status["failed"] = status.get("failed", 0) + 1
            status.setdefault("failed_vods", {})[vod_id] = str(e)
            log.warning(f"[{i+1}/{len(work_list)}] FAIL {vod_id}: {e}")

        # 임베딩 성공 후 영상 삭제 (--delete-after-embed 옵션)
        if embed_ok and args.delete_after_embed:
            delete_video_file(filepath)

        status["processed"] = status.get("processed", 0) + 1

        # pkl 모드: 배치 단위 저장
        if not use_parquet and len(batch_data) >= BATCH_SIZE:
            fname = save_batch(batch_data, batch_num)
            status.setdefault("batches_completed", []).append(fname)
            save_status(status, STATUS_FILE)
            batch_data = []
            batch_num  += 1

    # pkl 모드: 남은 항목 저장
    if not use_parquet and batch_data:
        fname = save_batch(batch_data, batch_num)
        status.setdefault("batches_completed", []).append(fname)

    # parquet 모드: 전체 결과 한 번에 저장
    if use_parquet and parquet_results:
        out_file = args.out_file or str(DATA_DIR / "embeddings_output.parquet")
        save_parquet(parquet_results, out_file)

    save_status(status, STATUS_FILE)
    print_status(status)
    log.info("배치 임베딩 완료")


if __name__ == "__main__":
    main()
