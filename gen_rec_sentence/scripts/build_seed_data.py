"""Phase 1: DB에서 VOD 메타 + 임베딩 조회 → Seed 데이터 템플릿 생성.

Usage:
    python gen_rec_sentence/scripts/build_seed_data.py
    python gen_rec_sentence/scripts/build_seed_data.py --limit 50 --output gen_rec_sentence/data/seed_examples.jsonl
"""

import argparse
import json
import logging
import sys

sys.path.insert(0, ".")

from gen_rec_sentence.src.context_builder import fetch_vod_contexts, get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=100, help="추출할 VOD 수 (기본 100)")
    parser.add_argument("--output", default="gen_rec_sentence/data/seed_examples.jsonl")
    parser.add_argument("--no-embedding", action="store_true", help="임베딩 없는 VOD도 포함")
    args = parser.parse_args()

    conn = get_conn()
    try:
        contexts = fetch_vod_contexts(
            conn,
            limit=args.limit,
            require_embedding=not args.no_embedding,
            require_poster=True,
        )
    finally:
        conn.close()

    # Seed 템플릿 형식으로 변환 (rec_sentence는 수작업으로 채울 빈칸)
    with open(args.output, "w", encoding="utf-8") as f:
        for ctx in contexts:
            record = {
                "instruction": "VOD의 메타데이터와 시각 키워드를 바탕으로 포스터 하단에 표시할 감성 문구를 생성하세요.",
                "input": {
                    "asset_nm": ctx["asset_nm"],
                    "genre": ctx["genre"],
                    "genre_detail": ctx["genre_detail"],
                    "director": ctx["director"],
                    "cast_lead": ctx["cast_lead"],
                    "smry": ctx["smry"][:300],
                    "rating": ctx["rating"],
                    "embedding": ctx["embedding"][:10],  # 미리보기용 10차원만 저장
                },
                "output": {
                    "rec_sentence": ""  # ← 수작업으로 채울 것
                },
                "vod_id": ctx["vod_id"],
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    log.info("Seed 템플릿 %d건 저장 → %s", len(contexts), args.output)
    log.info("rec_sentence 필드를 수작업으로 채워주세요.")


if __name__ == "__main__":
    main()
