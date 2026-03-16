"""
Tving 인덱스 빌드 스크립트.

사용:
    python Poster_Collection/scripts/build_tving_index.py
    python Poster_Collection/scripts/build_tving_index.py --force   # 재빌드
    python Poster_Collection/scripts/build_tving_index.py --workers 50
"""

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))

from Poster_Collection.src import tving_poster

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="기존 인덱스 무시하고 재빌드")
    parser.add_argument("--workers", type=int, default=30, help="병렬 작업자 수 (기본 30)")
    args = parser.parse_args()

    tving_poster.build_index(force=args.force, workers=args.workers)
