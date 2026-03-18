"""
CF_Engine 전체 파이프라인 실행

실행:
  python scripts/train.py                          # DB 학습 + 적재 (조장 전용)
  python scripts/train.py --dry-run                # DB 저장 없이 추천만 생성
  python scripts/train.py --output parquet         # 추천 결과 parquet 저장 (팀원용)
  python scripts/train.py --from-parquet <파일>    # parquet → DB 적재 (조장 전용)
"""

import sys
import time
import logging
import argparse
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from src.data_loader import get_conn, load_matrix
from src.als_model import train, recommend_all
from src.recommender import build_records
from src.content_recommender import (
    load_vod_content, load_quality_vod_ids,
    load_user_history_map, apply_content_boost,
)
from export_to_db import export

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_parquet(records: list[dict], out_path: Path) -> None:
    """추천 레코드 리스트 → parquet 저장."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        log.error("pyarrow 미설치 — pip install pyarrow")
        raise

    table = pa.table({
        "user_id_fk":          pa.array([r["user_id_fk"] for r in records], type=pa.string()),
        "vod_id_fk":           pa.array([r["vod_id_fk"] for r in records], type=pa.string()),
        "rank":                pa.array([r["rank"] for r in records], type=pa.int32()),
        "score":               pa.array([r["score"] for r in records], type=pa.float32()),
        "recommendation_type": pa.array([r["recommendation_type"] for r in records], type=pa.string()),
    })
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path)
    log.info("parquet 저장 완료: %s  (%d건)", out_path, len(records))


def load_parquet(parquet_path: Path) -> list[dict]:
    """parquet → 추천 레코드 리스트 로드."""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        log.error("pyarrow 미설치 — pip install pyarrow")
        raise

    table = pq.read_table(parquet_path)
    records = [
        {
            "user_id_fk": row["user_id_fk"].as_py(),
            "vod_id_fk":  row["vod_id_fk"].as_py(),
            "rank":        row["rank"].as_py(),
            "score":       float(row["score"].as_py()),
            "recommendation_type": row["recommendation_type"].as_py(),
        }
        for row in table.to_pylist()
    ]
    log.info("parquet 로드 완료: %s  (%d건)", parquet_path, len(records))
    return records


def run_pipeline(cfg: dict) -> tuple:
    """DB 로드 → ALS 학습 → 추천 생성 → 콘텐츠 후처리 → 레코드 변환. (mat shape 반환)"""
    m = cfg["model"]
    r = cfg["recommend"]
    c = cfg.get("content_boost", {})
    boost_enabled = c.get("enabled", True)
    min_count = c.get("min_count", 3)

    # ── 1차 연결: watch_history 로드 → ALS 학습 → 추천 생성 ────────
    conn = get_conn()
    log.info("DB 접속 완료")
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(conn, alpha=m["alpha"])
    conn.close()

    model = train(mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])
    user_ids, item_indices, scores = recommend_all(model, mat, top_k=r["top_k"])
    records = build_records(user_ids, item_indices, scores,
                            user_dec, item_dec,
                            recommendation_type=r["recommendation_type"])

    # ── 2차 연결: 콘텐츠 후처리 (ALS 학습 중 연결 유휴 방지) ──────
    if boost_enabled:
        log.info("콘텐츠 후처리 로드 중...")
        conn2 = get_conn()
        vod_content = load_vod_content(conn2)
        quality_vod_ids = load_quality_vod_ids(conn2)
        user_history_map = load_user_history_map(conn2)
        conn2.close()
        records = apply_content_boost(
            records, user_history_map, vod_content, quality_vod_ids,
            recommendation_type=r["recommendation_type"],
            min_count=min_count,
        )

    return records, mat.shape


def main():
    parser = argparse.ArgumentParser(description="CF_Engine 파이프라인")
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 저장 없이 추천 결과만 확인")
    parser.add_argument("--output", choices=["parquet"],
                        help="추천 결과 출력 방식 (parquet: 팀원용)")
    parser.add_argument("--from-parquet", metavar="FILE",
                        help="parquet 파일 → DB 적재 (조장 전용)")
    args = parser.parse_args()

    cfg = load_config(args.config)
    d = cfg["db"]
    r = cfg["recommend"]

    t0 = time.time()
    log.info("=" * 55)

    # ── 모드 1: parquet → DB 적재 (조장 전용) ──────────────────
    if args.from_parquet:
        log.info("from-parquet 모드 — %s → DB 적재", args.from_parquet)
        records = load_parquet(Path(args.from_parquet))
        conn = get_conn()
        export(conn, records, batch_size=d["batch_size"],
               recommendation_type=r["recommendation_type"])
        conn.close()
        log.info("완료  (소요: %.1f초)", time.time() - t0)
        return

    # ── 공통: DB 로드 → ALS 학습 → 추천 생성 ──────────────────
    log.info("CF_Engine 학습 시작")
    log.info("=" * 55)
    records, shape = run_pipeline(cfg)

    elapsed = time.time() - t0
    log.info("=" * 55)
    log.info("유저: %d명  |  아이템: %d개  |  추천: %d건  |  소요: %.1f초",
             shape[0], shape[1], len(records), elapsed)

    # ── 모드 2: parquet 저장 (팀원용) ──────────────────────────
    if args.output == "parquet":
        date_str = datetime.now().strftime("%Y%m%d")
        out_path = ROOT / "data" / f"cf_recommendations_{date_str}.parquet"
        save_parquet(records, out_path)

    # ── 모드 3: dry-run ─────────────────────────────────────────
    elif args.dry_run:
        log.info("dry-run 모드 — DB 저장 생략")

    # ── 모드 4: DB 직접 적재 (조장 전용) ───────────────────────
    else:
        conn = get_conn()
        export(conn, records, batch_size=d["batch_size"],
               recommendation_type=r["recommendation_type"])
        conn.close()

    log.info("완료")


if __name__ == "__main__":
    main()
