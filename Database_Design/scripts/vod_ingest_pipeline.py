"""
VOD 신규 추가 파이프라인 (트레일러 → PostgreSQL + pgvector)
============================================================
용도: 새로운 VOD 트레일러 영상을 시스템에 추가할 때 실행
사용법:
    python vod_ingest_pipeline.py --trailers-dir /path/to/trailers
    python vod_ingest_pipeline.py --pkl /path/to/video_embs.pkl
    python vod_ingest_pipeline.py --trailers-dir ./trailers --dry-run

처리 순서:
    1. trailers/*.webm → CLIP ViT-B/32 → 512차원 벡터 (또는 pkl 로드)
    2. 파일명 클리닝  → asset_nm 생성
    3. SHA-256 해시   → full_asset_id 생성 ("yt|{hash16}")
    4. OpenCV         → 영상 길이(초) 추출 → disp_rtm_sec
    5. PostgreSQL     → vod 테이블 INSERT (ON CONFLICT DO NOTHING)
    6. PostgreSQL     → vod_embedding 테이블 INSERT (벡터 + 메타데이터)

의존 패키지 (myenv 환경 기준):
    pip install psycopg2-binary python-dotenv
    # sentence-transformers, torch, opencv-python, Pillow: 이미 설치됨

full_asset_id 생성 규칙:
    기존 데이터: "cjc|M5068430LFOL10619301" (provider|code)
    신규 YouTube: "yt|{sha256(webm_filename)[:16]}"
    → 동일 파일명은 항상 동일한 ID 생성 (멱등성 보장)

asset_nm 생성 규칙:
    "About Time ｜ ＂Do You Want To...＂ (Domhnall Gleeson).webm"
    → "About Time"  (전각 파이프 ｜ 이전 텍스트, .webm 제거, strip)
    파이프 없으면 → 괄호 이전 텍스트 또는 전체 (확장자 제거)
"""

import argparse
import hashlib
import logging
import os
import pickle
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import psycopg2
from dotenv import load_dotenv
from PIL import Image

# =============================================================
# 경로 및 상수
# =============================================================

BASE_DIR           = Path(__file__).parent.parent
ENV_FILE           = BASE_DIR / ".env"
LOG_FILE           = Path(__file__).parent / "vod_ingest.log"
MODEL_DIR          = Path(r"C:\Users\daewo\DX_prod_2nd\my_clip_model")

EMBEDDING_DIM      = 512
EMBEDDING_TYPE     = "CLIP"
MODEL_VERSION      = "clip-ViT-B-32"
FRAME_SAMPLE_COUNT = 10   # 영상에서 균등 추출할 프레임 수

# =============================================================
# 로깅
# =============================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("vod_ingest")


# =============================================================
# DB 연결
# =============================================================

def get_pg_conn() -> psycopg2.extensions.connection:
    load_dotenv(ENV_FILE)
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "5432")),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=30,
    )


# =============================================================
# title → asset_nm 변환
# =============================================================

_PIPE_RE = re.compile(r'[｜|：]')   # 전각 파이프(｜), ASCII 파이프(|), 전각 콜론(：)


def clean_title_to_asset_nm(filename: str) -> str:
    """
    webm 파일명 → VOD 제목(asset_nm)으로 변환.

    규칙:
      1. 확장자(.webm, .mp4 등) 제거
      2. 전각/ASCII 파이프(｜|) 이전 텍스트 추출
         → 없으면 괄호 이전 텍스트
         → 없으면 전체 텍스트
      3. 연속 공백 정리

    예시:
      "About Time ｜ ＂Do You Want...＂.webm"    → "About Time"
      "Ana & Christian's Most Romantic Moments.webm" → "Ana & Christian's Most Romantic Moments"
      "Frankenstein (1931) ｜ Monster Vs....webm"    → "Frankenstein (1931)"
    """
    stem = Path(filename).stem
    parts = _PIPE_RE.split(stem, maxsplit=1)
    if len(parts) > 1:
        name = parts[0].strip()
    else:
        bracket_match = re.match(r'^(.+?)\s*[\(\[]', stem)
        name = bracket_match.group(1).strip() if bracket_match else stem.strip()
    return re.sub(r'\s+', ' ', name).strip()


# =============================================================
# full_asset_id 생성
# =============================================================

def generate_full_asset_id(filename: str) -> str:
    """
    webm 파일명 기반 고유 ID 생성.
    형식: "yt|{sha256(filename)[:16]}"
    동일 파일명 → 동일 ID → 멱등성 보장
    """
    hash16 = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:16]
    return f"yt|{hash16}"


# =============================================================
# 영상 처리
# =============================================================

def get_video_duration_sec(video_path: str) -> int:
    """OpenCV로 영상 총 길이(초) 추출."""
    cap = cv2.VideoCapture(video_path)
    fps         = cap.get(cv2.CAP_PROP_FPS)
    total_frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    if fps > 0 and total_frames > 0:
        return max(1, int(total_frames / fps))
    return 0


def get_video_embedding(video_path: str, model) -> "np.ndarray | None":
    """
    영상에서 FRAME_SAMPLE_COUNT개 프레임 균등 추출 후 CLIP 임베딩 평균.
    notebook의 get_video_embedding()과 동일한 로직.
    반환: float32 numpy array (512,) 또는 None
    """
    import torch

    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        cap.release()
        return None

    step   = max(1, total_frames // FRAME_SAMPLE_COUNT)
    frames = []
    for i in range(FRAME_SAMPLE_COUNT):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i * step)
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)))
    cap.release()

    if not frames:
        return None

    with torch.no_grad():
        embeddings = model.encode(frames, convert_to_tensor=True, show_progress_bar=False)
        vec = torch.mean(embeddings, dim=0).cpu().numpy().astype(np.float32)
    return vec


# =============================================================
# CLIP 모델 로드
# =============================================================

def load_clip_model():
    from sentence_transformers import SentenceTransformer
    if MODEL_DIR.exists():
        log.info(f"로컬 모델 로드: {MODEL_DIR}")
        return SentenceTransformer(str(MODEL_DIR))
    log.info("로컬 모델 없음 → HuggingFace에서 다운로드")
    return SentenceTransformer("clip-ViT-B-32")


# =============================================================
# 벡터 → pgvector 포맷 변환
# =============================================================

def to_pgvector_str(vec: np.ndarray) -> str:
    """
    numpy float32 배열 → pgvector 리터럴 문자열.
    예: '[0.12345678, -0.98765432, ...]'
    psycopg2에서 %s::vector 로 바인딩하면 pgvector가 파싱.
    """
    return '[' + ','.join(f'{x:.8f}' for x in vec) + ']'


# =============================================================
# PostgreSQL INSERT
# =============================================================

def insert_vod(conn, vod: dict, dry_run: bool = False) -> bool:
    """
    vod 테이블에 신규 VOD 삽입.
    ON CONFLICT DO NOTHING → 이미 존재하면 건너뜀.
    반환: True=신규삽입, False=이미존재
    """
    sql = """
        INSERT INTO vod (
            full_asset_id, asset_nm, ct_cl,
            disp_rtm, disp_rtm_sec,
            genre, provider, created_at
        ) VALUES (
            %(full_asset_id)s, %(asset_nm)s, %(ct_cl)s,
            %(disp_rtm)s, %(disp_rtm_sec)s,
            %(genre)s, %(provider)s, NOW()
        )
        ON CONFLICT (full_asset_id) DO NOTHING
        RETURNING full_asset_id
    """
    if dry_run:
        log.info(f"  [DRY-RUN] vod INSERT: {vod['full_asset_id']} / {vod['asset_nm']}")
        return True

    with conn.cursor() as cur:
        cur.execute(sql, vod)
        inserted = cur.fetchone() is not None
    conn.commit()
    return inserted


def insert_vod_embedding(conn, emb: dict, dry_run: bool = False) -> None:
    """
    vod_embedding 테이블에 벡터 + 메타데이터 삽입.
    ON CONFLICT (vod_id_fk) DO UPDATE → 재실행 시 벡터 갱신.
    벡터는 %s::vector 캐스팅으로 pgvector에 전달 (추가 패키지 불필요).
    """
    sql = """
        INSERT INTO vod_embedding (
            vod_id_fk,
            embedding,
            embedding_type, embedding_dim, model_version,
            vector_magnitude, frame_count, source_type
        ) VALUES (
            %(vod_id_fk)s,
            %(embedding)s::vector,
            %(embedding_type)s, %(embedding_dim)s, %(model_version)s,
            %(vector_magnitude)s, %(frame_count)s, %(source_type)s
        )
        ON CONFLICT (vod_id_fk) DO UPDATE SET
            embedding        = EXCLUDED.embedding,
            vector_magnitude = EXCLUDED.vector_magnitude,
            updated_at       = NOW()
    """
    if dry_run:
        log.info(f"  [DRY-RUN] vod_embedding INSERT: {emb['vod_id_fk']}")
        return

    with conn.cursor() as cur:
        cur.execute(sql, emb)
    conn.commit()


# =============================================================
# 단일 VOD 처리
# =============================================================

def process_one(
    *,
    title: str,
    vec_np: "np.ndarray | None",   # 이미 numpy로 변환된 벡터 (pkl 모드)
    video_path: "str | None",       # 영상 파일 경로 (trailers 모드)
    model,
    conn,
    dry_run: bool,
) -> None:
    log.info(f"처리 시작: {title}")

    # 1. 벡터 준비
    if vec_np is None:
        if video_path is None:
            log.warning(f"  벡터도 파일도 없음 → 건너뜀: {title}")
            return
        vec_np = get_video_embedding(video_path, model)
        if vec_np is None:
            log.warning(f"  임베딩 실패 → 건너뜀: {title}")
            return

    magnitude = float(np.linalg.norm(vec_np))
    vec_str   = to_pgvector_str(vec_np)

    # 2. 메타 정보
    asset_nm      = clean_title_to_asset_nm(title)
    full_asset_id = generate_full_asset_id(title)

    # 3. 영상 길이
    duration_sec = 0
    if video_path and os.path.exists(video_path):
        duration_sec = get_video_duration_sec(video_path)
    minutes, seconds = divmod(duration_sec, 60)
    disp_rtm = f"{minutes:02d}:{seconds:02d}" if duration_sec > 0 else "00:00"

    log.info(f"  full_asset_id : {full_asset_id}")
    log.info(f"  asset_nm      : {asset_nm}")
    log.info(f"  길이          : {duration_sec}초 ({disp_rtm})")
    log.info(f"  벡터          : {len(vec_np)}차원, magnitude={magnitude:.4f}")

    # 4. vod 테이블 INSERT
    is_new = insert_vod(conn, {
        "full_asset_id": full_asset_id,
        "asset_nm":      asset_nm,
        "ct_cl":         "영화",       # 트레일러 기본값 — RAG 파이프라인에서 보완 예정
        "disp_rtm":      disp_rtm,
        "disp_rtm_sec":  max(1, duration_sec),
        "genre":         None,
        "provider":      "YouTube",
    }, dry_run=dry_run)
    log.info(f"  vod: {'신규 삽입' if is_new else '이미 존재 (스킵)'}")

    # 5. vod_embedding 테이블 INSERT (벡터 포함)
    insert_vod_embedding(conn, {
        "vod_id_fk":       full_asset_id,
        "embedding":       vec_str,
        "embedding_type":  EMBEDDING_TYPE,
        "embedding_dim":   EMBEDDING_DIM,
        "model_version":   MODEL_VERSION,
        "vector_magnitude": magnitude,
        "frame_count":     FRAME_SAMPLE_COUNT,
        "source_type":     "TRAILER",
    }, dry_run=dry_run)
    log.info(f"  vod_embedding: 저장 완료")
    log.info(f"처리 완료: {title}")


# =============================================================
# 메인
# =============================================================

def parse_args():
    parser = argparse.ArgumentParser(description="VOD 신규 추가 파이프라인 (pgvector)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--trailers-dir", type=str,
        help="트레일러 영상 폴더 경로 (*.webm, *.mp4 처리)",
    )
    group.add_argument(
        "--pkl", type=str,
        help="video_embs.pkl 파일 경로 (이미 임베딩된 경우)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="DB INSERT 없이 처리 결과만 출력",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    load_dotenv(ENV_FILE)

    log.info("=" * 60)
    log.info("VOD 신규 추가 파이프라인 시작 (pgvector)")
    log.info(f"dry_run={args.dry_run}")
    log.info("=" * 60)

    conn = get_pg_conn() if not args.dry_run else None
    if args.dry_run:
        log.info("[DRY-RUN 모드] DB 연결 없이 실행")

    # ── pkl 모드 ──────────────────────────────────────────────
    if args.pkl:
        log.info(f"pkl 로드: {args.pkl}")
        with open(args.pkl, "rb") as f:
            video_db = pickle.load(f)
        log.info(f"총 {len(video_db)}개 항목")

        for item in video_db:
            # torch.Tensor → numpy 변환
            vec = item["vector"]
            if hasattr(vec, "cpu"):
                vec_np = vec.cpu().numpy().astype(np.float32)
            else:
                vec_np = np.array(vec, dtype=np.float32)

            process_one(
                title=item["title"],
                vec_np=vec_np,
                video_path=None,
                model=None,
                conn=conn,
                dry_run=args.dry_run,
            )

    # ── trailers 디렉토리 모드 ────────────────────────────────
    else:
        trailers_dir = Path(args.trailers_dir)
        video_files  = sorted(
            f for f in trailers_dir.iterdir()
            if f.suffix.lower() in (".webm", ".mp4", ".mkv", ".avi")
        )
        if not video_files:
            log.warning(f"영상 파일 없음: {trailers_dir}")
            return

        log.info(f"총 {len(video_files)}개 영상 처리 시작: {trailers_dir}")
        model = load_clip_model()

        for video_file in video_files:
            process_one(
                title=video_file.name,
                vec_np=None,
                video_path=str(video_file),
                model=model,
                conn=conn,
                dry_run=args.dry_run,
            )

    if conn:
        conn.close()

    log.info("=" * 60)
    log.info("파이프라인 완료")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
