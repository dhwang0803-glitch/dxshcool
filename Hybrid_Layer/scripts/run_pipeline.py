"""Hybrid_Layer 전체 파이프라인 실행 (Phase 1 → 2 → 3 → 4).

Usage:
    python Hybrid_Layer/scripts/run_pipeline.py
    python Hybrid_Layer/scripts/run_pipeline.py --beta 0.7 --top-n 10

Phase 1: vod → vod_tag (TMDB confidence 기반 재적재)
Phase 2: watch_history × vod_tag → user_preference
Phase 3: CF+Vector 후보 리랭킹 → hybrid_recommendation
Phase 4: 선호 태그별 VOD 선반 → tag_recommendation
"""

import argparse
import logging
import sys
import time

import yaml

sys.path.insert(0, ".")

from Hybrid_Layer.src.db import get_conn
from Hybrid_Layer.src.tag_builder import build_vod_tags
from Hybrid_Layer.src.preference_builder import build_user_preferences
from Hybrid_Layer.src.reranker import run_hybrid_reranking
from Hybrid_Layer.src.shelf_builder import build_tag_shelves

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    with open("Hybrid_Layer/config/hybrid_config.yaml", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    rr = config.get("reranking", {})
    tr = config.get("tag_recommendation", {})
    batch = config.get("batch", {})

    parser = argparse.ArgumentParser(description="Hybrid_Layer 전체 파이프라인")
    parser.add_argument("--beta", type=float, default=rr.get("beta", 0.6))
    parser.add_argument("--top-n", type=int, default=rr.get("top_n", 10))
    parser.add_argument("--top-k-tags", type=int, default=rr.get("top_k_tags", 3))
    parser.add_argument("--vods-per-tag", type=int, default=tr.get("vods_per_tag", 10))
    parser.add_argument("--chunk-size", type=int, default=batch.get("user_chunk_size", 1000))
    parser.add_argument(
        "--test-mode", action="store_true",
        help="테스터 격리 모드: Phase 2~4를 _test 테이블 대상으로 실행 (Phase 1 제외)",
    )
    args = parser.parse_args()

    pipeline_start = time.time()
    results = {}

    # ── Phase 1 ──────────────────────────────────────────────
    # vod_tag는 전체 공용 데이터 → test_mode와 무관하게 항상 실행
    log.info("=" * 60)
    log.info("Phase 1: vod → vod_tag (TMDB confidence 기반)")
    log.info("=" * 60)
    t = time.time()
    conn = get_conn()
    try:
        results["phase1"] = build_vod_tags(conn)
    finally:
        conn.close()
    log.info("Phase 1 완료: %d tags | 소요: %.1f분", results["phase1"], (time.time() - t) / 60)

    # ── Phase 2 ──────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Phase 2: watch_history × vod_tag → user_preference")
    log.info("=" * 60)
    t = time.time()
    conn = get_conn()
    try:
        results["phase2"] = build_user_preferences(conn, test_mode=args.test_mode)
    finally:
        conn.close()
    log.info("Phase 2 완료: %d rows | 소요: %.1f분", results["phase2"], (time.time() - t) / 60)

    # ── Phase 3 ──────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Phase 3: CF+Vector 후보 리랭킹 → hybrid_recommendation")
    log.info("=" * 60)
    t = time.time()
    conn = get_conn()
    try:
        results["phase3"] = run_hybrid_reranking(
            conn,
            beta=args.beta,
            top_n=args.top_n,
            top_k_tags=args.top_k_tags,
            user_chunk_size=args.chunk_size,
            test_mode=args.test_mode,
        )
    finally:
        conn.close()
    log.info("Phase 3 완료: %d rows | 소요: %.1f분", results["phase3"], (time.time() - t) / 60)

    # ── Phase 4 ──────────────────────────────────────────────
    log.info("=" * 60)
    log.info("Phase 4: 선호 태그별 VOD 선반 → tag_recommendation")
    log.info("=" * 60)
    t = time.time()
    conn = get_conn()
    try:
        results["phase4"] = build_tag_shelves(
            conn,
            vods_per_tag=args.vods_per_tag,
            user_chunk_size=args.chunk_size,
            test_mode=args.test_mode,
        )
    finally:
        conn.close()
    log.info("Phase 4 완료: %d rows | 소요: %.1f분", results["phase4"], (time.time() - t) / 60)

    # ── 최종 요약 ─────────────────────────────────────────────
    total_min = (time.time() - pipeline_start) / 60
    log.info("=" * 60)
    log.info("파이프라인 완료 | 총 소요: %.1f분 (%.1f시간)", total_min, total_min / 60)
    log.info("  Phase 1 vod_tag:              %10d rows", results["phase1"])
    log.info("  Phase 2 user_preference:      %10d rows", results["phase2"])
    log.info("  Phase 3 hybrid_recommendation:%10d rows", results["phase3"])
    log.info("  Phase 4 tag_recommendation:   %10d rows", results["phase4"])
    log.info("=" * 60)


if __name__ == "__main__":
    main()
