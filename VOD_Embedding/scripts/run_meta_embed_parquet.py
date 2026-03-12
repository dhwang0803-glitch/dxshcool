"""
VOD 메타데이터 임베딩 → Parquet 저장 스크립트

DB 쓰기 권한 없이 실행 가능.
vod_meta_embedding 테이블이 생성되면 ingest_to_db.py로 적재.

출력 파일: data/vod_meta_embedding_<날짜>.parquet
체크포인트: data/meta_embed_checkpoint.json (20 시리즈마다 저장)
컬럼:
    vod_id_fk       : str   (vod.full_asset_id)
    embedding       : list  (384차원 float32)
    input_text      : str   (임베딩에 사용된 텍스트)
    model_name      : str
    embedding_dim   : int
    vector_magnitude: float (정규화 시 1.0)
    created_at      : str   (ISO 8601)

실행:
    cd VOD_Embedding
    # DB 권한 없는 팀원 — parquet 출력 (기존 동작)
    python scripts/run_meta_embed_parquet.py
    python scripts/run_meta_embed_parquet.py --output data/my_output.parquet

    # DB 권한 있는 조장 — 임베딩 계산 후 DB 직접 적재
    python scripts/run_meta_embed_parquet.py --upload-db

    # 이미 생성된 parquet → DB 직접 적재 (임베딩 재계산 없음)
    python scripts/run_meta_embed_parquet.py \
        --from-parquet data/vod_meta_embedding_20260311.parquet \
        --upload-db

재시작 시 체크포인트에서 자동 이어받기 (parquet 모드).
"""
import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from sentence_transformers import SentenceTransformer

# src/ 경로를 모듈 탐색 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import config
from db import fetch_all_as_dict, get_conn
from meta_embedder import build_vod_text, group_by_series, pick_representative

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

ENCODE_BATCH_SIZE   = 128
CHECKPOINT_INTERVAL = 20     # 시리즈 단위 체크포인트 저장 주기
COMMIT_INTERVAL     = 1_000  # DB 적재 시 COMMIT 주기

DATA_DIR        = Path(__file__).parent.parent / "data"
CHECKPOINT_FILE = DATA_DIR / "meta_embed_checkpoint.json"

# vod_meta_embedding 적재 상수
SOURCE_FIELDS   = ["asset_nm", "genre", "director", "cast_lead", "smry"]

INSERT_META_SQL = """
INSERT INTO vod_meta_embedding (
    vod_id_fk, embedding, input_text, model_name, source_fields
)
VALUES (
    %(vod_id_fk)s, %(embedding)s::vector,
    %(input_text)s, %(model_name)s, %(source_fields)s
)
ON CONFLICT (vod_id_fk)
DO UPDATE SET
    embedding    = EXCLUDED.embedding,
    input_text   = EXCLUDED.input_text,
    updated_at   = NOW()
"""


# ---------------------------------------------------------------------------
# DB 적재 헬퍼
# ---------------------------------------------------------------------------

def to_pgvector_str(vec) -> str:
    """list/ndarray → '[f1,f2,...,f384]' 문자열 (pgvector 형식)"""
    return '[' + ','.join(f'{x:.8f}' for x in vec) + ']'


def ingest_records_to_db(records: list) -> None:
    """accumulated records를 vod_meta_embedding 테이블에 적재"""
    logger.info(f"DB 적재 시작: {len(records):,}건 → public.vod_meta_embedding")
    inserted = 0
    with get_conn() as conn:
        cur = conn.cursor()
        for i, rec in enumerate(records):
            cur.execute(INSERT_META_SQL, {
                "vod_id_fk":     rec["vod_id_fk"],
                "embedding":     to_pgvector_str(rec["embedding"]),
                "input_text":    rec.get("input_text", ""),
                "model_name":    rec.get("model_name", config.EMBEDDING_MODEL),
                "source_fields": SOURCE_FIELDS,
            })
            inserted += 1
            if (i + 1) % COMMIT_INTERVAL == 0:
                conn.commit()
                logger.info(f"  COMMIT ({i+1:,}/{len(records):,}건)")
    logger.info(f"DB 적재 완료: {inserted:,}건")


def upload_from_parquet(parquet_path: str) -> None:
    """기존 parquet 파일을 DB에 직접 적재 (임베딩 재계산 없음)"""
    p = Path(parquet_path)
    if not p.exists():
        logger.error(f"파일 없음: {p}")
        sys.exit(1)
    logger.info(f"Parquet 로드: {p}")
    df = pd.read_parquet(p)
    records = df.to_dict("records")
    logger.info(f"  {len(records):,}건 로드")
    ingest_records_to_db(records)


# ---------------------------------------------------------------------------
# 체크포인트 로드 / 저장
# ---------------------------------------------------------------------------

def load_checkpoint() -> dict:
    if CHECKPOINT_FILE.exists():
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            ckpt = json.load(f)
        logger.info(
            f"체크포인트 로드: {ckpt['done_series']:,}개 시리즈 / "
            f"{ckpt['done_vod_count']:,}건 완료 (마지막: {ckpt['last_updated']})"
        )
        return ckpt
    return {
        "done_series":    0,
        "total_series":   0,
        "done_vod_count": 0,
        "done_series_keys": [],   # 완료된 시리즈 키 목록 (str 변환)
        "last_updated":   None,
        "output_path":    None,
    }


def save_checkpoint(ckpt: dict) -> None:
    ckpt["last_updated"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
        json.dump(ckpt, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# VOD 조회
# ---------------------------------------------------------------------------

def fetch_all_vods() -> list:
    """
    전체 VOD 메타데이터 조회.
    is_active 컬럼이 없으므로 WHERE 조건 없이 전체 조회.
    """
    logger.info("VOD 메타데이터 로딩 중...")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    full_asset_id,
                    asset_nm,
                    ct_cl,
                    genre,
                    genre_detail,
                    director,
                    cast_lead,
                    cast_guest,
                    smry,
                    release_date
                FROM vod
                ORDER BY full_asset_id
            """)
            rows = fetch_all_as_dict(cur)
    logger.info(f"  전체 VOD: {len(rows):,}건 로드 완료")
    return rows


# ---------------------------------------------------------------------------
# 메인 파이프라인
# ---------------------------------------------------------------------------

def run(output_path: str, upload_db: bool = False) -> None:
    logger.info("=== VOD 메타데이터 임베딩 → Parquet 파이프라인 시작 ===")

    # 1. 체크포인트 로드
    ckpt = load_checkpoint()
    done_keys = set(ckpt["done_series_keys"])

    # 출력 경로: 체크포인트에 저장된 경로 우선 (이어받기 시 동일 파일 유지)
    if ckpt["output_path"] and Path(ckpt["output_path"]).exists():
        output_path = ckpt["output_path"]
        logger.info(f"  이어받기 모드 — 출력 파일: {output_path}")
    else:
        ckpt["output_path"] = output_path

    # 기존 Parquet에서 누적 records 로드
    out = Path(output_path)
    if out.exists() and done_keys:
        existing_df = pd.read_parquet(out)
        accumulated = existing_df.to_dict("records")
        logger.info(f"  기존 Parquet 로드: {len(accumulated):,}건")
    else:
        accumulated = []

    # 2. 모델 로드
    logger.info(f"임베딩 모델 로드: {config.EMBEDDING_MODEL}")
    model = SentenceTransformer(config.EMBEDDING_MODEL)

    # 3. VOD 조회 및 시리즈 그룹핑
    all_vods = fetch_all_vods()
    series_groups = group_by_series(all_vods)
    series_list   = list(series_groups.items())
    total_series  = len(series_list)
    total_rows    = len(all_vods)
    logger.info(f"  시리즈 그룹: {total_series:,}개 / 전체 row: {total_rows:,}건")

    ckpt["total_series"] = total_series

    # 4. 미완료 시리즈만 필터링
    pending = [(key, vods) for key, vods in series_list if str(key) not in done_keys]
    logger.info(f"  미완료 시리즈: {len(pending):,}개 (완료: {len(done_keys):,}개 스킵)")

    if not pending:
        logger.info("모든 시리즈 처리 완료. 종료합니다.")
        return

    # 5. 청크 단위 인코딩 + 즉시 체크포인트 저장
    now_iso = datetime.now(timezone.utc).isoformat()
    done_cnt = 0
    out.parent.mkdir(parents=True, exist_ok=True)

    for chunk_start in range(0, len(pending), CHECKPOINT_INTERVAL):
        chunk = pending[chunk_start:chunk_start + CHECKPOINT_INTERVAL]

        # 청크 내 대표 텍스트 수집
        chunk_texts = []
        for _, group_vods in chunk:
            rep  = pick_representative(group_vods)
            text = build_vod_text(rep).strip() or rep.get("asset_nm") or ""
            if not text:
                logger.warning(f"빈 텍스트 스킵 — full_asset_id={rep['full_asset_id']}")
            chunk_texts.append(text or None)

        valid_indices = [i for i, t in enumerate(chunk_texts) if t is not None]
        valid_texts   = [chunk_texts[i] for i in valid_indices]

        if not valid_texts:
            for key, group_vods in chunk:
                done_keys.add(str(key))
                ckpt["done_series"] += 1
            continue

        # 청크 인코딩
        vectors = model.encode(
            valid_texts,
            batch_size=ENCODE_BATCH_SIZE,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        vec_map = {valid_indices[i]: vectors[i] for i in range(len(valid_indices))}

        # records 생성
        for i, (key, group_vods) in enumerate(chunk):
            if i in vec_map:
                vec        = vec_map[i]
                rep        = pick_representative(group_vods)
                input_text = build_vod_text(rep).strip()
                for vod in group_vods:
                    accumulated.append({
                        "vod_id_fk":        vod["full_asset_id"],
                        "embedding":        vec.tolist(),
                        "input_text":       input_text,
                        "model_name":       config.EMBEDDING_MODEL,
                        "embedding_dim":    config.EMBEDDING_DIM,
                        "vector_magnitude": 1.0,
                        "created_at":       now_iso,
                    })
                ckpt["done_vod_count"] += len(group_vods)
            done_keys.add(str(key))
            ckpt["done_series"] += 1
            done_cnt += 1

        # 청크마다 체크포인트 저장
        ckpt["done_series_keys"] = list(done_keys)
        pd.DataFrame(accumulated).to_parquet(out, index=False)
        save_checkpoint(ckpt)
        logger.info(
            f"체크포인트 저장 — 시리즈 {ckpt['done_series']:,}/{total_series:,} "
            f"({ckpt['done_series']/total_series*100:.1f}%) | row {ckpt['done_vod_count']:,}건"
        )

    # 6. 최종 저장 (parquet 항상 보존)
    ckpt["done_series_keys"] = list(done_keys)
    df = pd.DataFrame(accumulated)
    df.to_parquet(out, index=False)
    save_checkpoint(ckpt)
    logger.info(f"저장 완료: {out} ({len(df):,}건, {out.stat().st_size / 1024 / 1024:.1f} MB)")

    # 7. DB 적재 (--upload-db 옵션, 권한 없으면 parquet 백업 보존)
    if upload_db:
        try:
            ingest_records_to_db(accumulated)
        except Exception as e:
            logger.error(f"DB 적재 실패 — parquet 백업 보존됨: {e}")

    logger.info("=== 완료 ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VOD 메타데이터 임베딩 → Parquet / DB 적재")
    parser.add_argument(
        "--output",
        default=f"data/vod_meta_embedding_{datetime.now().strftime('%Y%m%d')}.parquet",
        help="출력 Parquet 파일 경로 (기본: data/vod_meta_embedding_YYYYMMDD.parquet)",
    )
    parser.add_argument(
        "--upload-db",
        action="store_true",
        help="임베딩을 vod_meta_embedding 테이블에 DB 적재 (권한 없으면 parquet 저장으로 대체)",
    )
    parser.add_argument(
        "--from-parquet",
        default="",
        metavar="PARQUET_PATH",
        help="기존 parquet 파일을 DB에 직접 적재 (--upload-db 필요, 임베딩 재계산 생략)",
    )
    args = parser.parse_args()

    if args.from_parquet:
        if not args.upload_db:
            logger.error("--from-parquet 사용 시 --upload-db 옵션 필요")
            sys.exit(1)
        upload_from_parquet(args.from_parquet)
    else:
        run(args.output, upload_db=args.upload_db)
