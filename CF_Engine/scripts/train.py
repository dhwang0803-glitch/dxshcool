"""
CF_Engine 전체 파이프라인 실행

실행: python scripts/train.py
      python scripts/train.py --config config/als_config.yaml
      python scripts/train.py --dry-run   # DB 저장 없이 추천만 생성
"""

import sys
import time
import logging
import argparse
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))           # src/ 임포트용
sys.path.insert(0, str(ROOT / "scripts"))  # export_to_db 임포트용
sys.stdout.reconfigure(encoding="utf-8")

from src.data_loader import get_conn, load_matrix
from src.als_model import train, recommend_all
from src.recommender import build_records
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/als_config.yaml")
    parser.add_argument("--dry-run", action="store_true",
                        help="DB 저장 없이 추천 결과만 생성")
    args = parser.parse_args()

    cfg = load_config(args.config)
    m = cfg["model"]
    r = cfg["recommend"]
    d = cfg["db"]

    t0 = time.time()
    log.info("=" * 55)
    log.info("CF_Engine 학습 시작")
    log.info("=" * 55)

    conn = get_conn()
    log.info("DB 접속 완료")

    # STEP 1: 데이터 로드
    mat, user_enc, item_enc, user_dec, item_dec = load_matrix(conn, alpha=m["alpha"])

    # STEP 2: ALS 학습
    model = train(mat, factors=m["factors"], iterations=m["iterations"],
                  regularization=m["regularization"])

    # STEP 3: 추천 생성
    user_ids, item_indices, scores = recommend_all(model, mat, top_k=r["top_k"])

    # STEP 4: 레코드 변환
    records = build_records(user_ids, item_indices, scores,
                            user_dec, item_dec,
                            recommendation_type=r["recommendation_type"])

    elapsed = time.time() - t0
    log.info("=" * 55)
    log.info("유저: %d명  |  아이템: %d개  |  추천: %d건  |  소요: %.1f초",
             mat.shape[0], mat.shape[1], len(records), elapsed)

    if args.dry_run:
        log.info("dry-run 모드 — DB 저장 생략")
    else:
        export(conn, records, batch_size=d["batch_size"],
               recommendation_type=r["recommendation_type"])

    conn.close()
    log.info("완료")


if __name__ == "__main__":
    main()
