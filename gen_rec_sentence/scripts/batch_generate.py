"""Phase 4: 배치 문구 생성 → serving.rec_sentence 적재.

DB 왕복 계획:
  읽기: vod + vod_embedding dump (1회)
  쓰기: rec_sentence UPSERT 배치 (~수십 회, 500행 단위)
  총계: ~수십 회

Usage:
    python gen_rec_sentence/scripts/batch_generate.py
    python gen_rec_sentence/scripts/batch_generate.py --limit 1000 --model gemma2:9b
"""

import argparse
import logging
import sys
import time

import psycopg2

sys.path.insert(0, ".")

from gen_rec_sentence.src.context_builder import fetch_vod_contexts, get_conn
from gen_rec_sentence.src.quality_filter import filter_batch
from gen_rec_sentence.src.sentence_generator import generate_sentence

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_INSERT_BATCH = 500


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--model", default="gemma2:9b")
    parser.add_argument("--temperature", type=float, default=0.7)
    args = parser.parse_args()

    conn = get_conn()
    try:
        # ── Step 1: 전체 VOD 컨텍스트 dump (1회) ───────────────────────────
        log.info("[1/3] VOD 컨텍스트 dump...")
        contexts = fetch_vod_contexts(conn, limit=args.limit, require_embedding=True, require_poster=True)
        log.info("  → %d VOD 로드", len(contexts))

        # ── Step 2: 생성 + 품질 필터 (Ollama, DB 왕복 없음) ─────────────────
        log.info("[2/3] rec_sentence 생성 중...")
        results = []
        for i, ctx in enumerate(contexts):
            result = generate_sentence(ctx, model=args.model, temperature=args.temperature)
            results.append(result)
            if (i + 1) % 100 == 0:
                log.info("  생성 진행: %d/%d", i + 1, len(contexts))
            time.sleep(0.1)  # Ollama rate limit 여유

        passed, failed = filter_batch(results, contexts)
        log.info("  → 통과: %d / 실패: %d", len(passed), len(failed))

        # ── Step 3: 배치 UPSERT ─────────────────────────────────────────────
        log.info("[3/3] serving.rec_sentence UPSERT...")
        total_upserted = 0
        for i in range(0, len(passed), _INSERT_BATCH):
            batch = passed[i:i + _INSERT_BATCH]
            with conn.cursor() as cur:
                args_str = ",".join(
                    cur.mogrify(
                        "(%s,%s,%s,%s)",
                        (r["vod_id"], r["rec_sentence"], r["embedding_used"], r["model_name"])
                    ).decode()
                    for r in batch
                )
                cur.execute(
                    f"""
                    INSERT INTO serving.rec_sentence
                        (vod_id_fk, rec_sentence, embedding_used, model_name)
                    VALUES {args_str}
                    ON CONFLICT (vod_id_fk) DO UPDATE SET
                        rec_sentence = EXCLUDED.rec_sentence,
                        embedding_used = EXCLUDED.embedding_used,
                        model_name = EXCLUDED.model_name,
                        generated_at = NOW(),
                        expires_at = NOW() + INTERVAL '30 days'
                    """
                )
                total_upserted += cur.rowcount
            conn.commit()
            log.info("  UPSERT 진행: %d/%d", min(i + _INSERT_BATCH, len(passed)), len(passed))

        log.info("완료: %d건 적재 | 실패 %d건은 data/failed_sentences.jsonl 확인", total_upserted, len(failed))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
