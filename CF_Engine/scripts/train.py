"""
CF_Engine 전체 파이프라인 실행

실행:
  python scripts/train.py                # DB 학습 + 적재
  python scripts/train.py --dry-run      # DB 저장 없이 추천만 생성
"""

import sys
import time
import logging
import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(encoding="utf-8")

from src.data_loader import get_conn, load_matrix
from src.als_model import train, recommend_all
from src.recommender import build_records, load_vod_series_map
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


def run_pipeline(cfg: dict) -> tuple:
    """DB 로드 → ALS 학습 → 추천 생성 → 시리즈 중복 제거 → 레코드 변환. (mat shape 반환)"""
    m = cfg["model"]
    r = cfg["recommend"]
    top_k = r["top_k"]

    conn = get_conn()
    log.info("DB 접속 완료")
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(conn, alpha=m["alpha"])
    vod_series_map = load_vod_series_map(conn)
    conn.close()

    model = train(mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])
    user_ids, item_indices, scores = recommend_all(model, mat, top_k=top_k)
    records = build_records(user_ids, item_indices, scores,
                            user_dec, item_dec,
                            recommendation_type=r["recommendation_type"],
                            top_k=top_k,
                            vod_series_map=vod_series_map)

    return records, mat.shape


def main():
    parser = argparse.ArgumentParser(description="CF_Engine 파이프라인")
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 저장 없이 추천 결과만 확인")
    args = parser.parse_args()

    cfg = load_config(args.config)
    d = cfg["db"]
    r = cfg["recommend"]

    t0 = time.time()
    log.info("=" * 55)
    log.info("CF_Engine 학습 시작")
    log.info("=" * 55)
    records, shape = run_pipeline(cfg)

    elapsed = time.time() - t0
    log.info("=" * 55)
    log.info("유저: %d명  |  아이템: %d개  |  추천: %d건  |  소요: %.1f초",
             shape[0], shape[1], len(records), elapsed)

    if args.dry_run:
        log.info("dry-run 모드 — DB 저장 생략")
    else:
        conn = get_conn()
        export(conn, records, batch_size=d["batch_size"],
               recommendation_type=r["recommendation_type"])
        conn.close()

    log.info("완료")


if __name__ == "__main__":
    main()
