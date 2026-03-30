"""Phase 5: 튜닝 전후 품질 비교 평가.

Usage:
    python gen_rec_sentence/scripts/evaluate_model.py \
        --eval-set gen_rec_sentence/data/eval_results.jsonl \
        --model gemma2:9b \
        --tuned-model gemma2-rec:latest
"""

import argparse
import json
import logging
import sys

sys.path.insert(0, ".")

from gen_rec_sentence.src.context_builder import fetch_vod_contexts, get_conn
from gen_rec_sentence.src.quality_filter import validate
from gen_rec_sentence.src.sentence_generator import generate_sentence

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def evaluate_model(contexts: list[dict], model: str) -> dict:
    results = []
    for ctx in contexts:
        r = generate_sentence(ctx, model=model)
        validated = validate(r, ctx)
        results.append(validated)

    total = len(results)
    passed = sum(1 for r in results if r.get("pass"))
    avg_len = sum(len(r.get("rec_sentence") or "") for r in results) / total if total else 0

    return {
        "model": model,
        "total": total,
        "pass_rate": round(passed / total, 3) if total else 0,
        "avg_length": round(avg_len, 1),
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50, help="평가할 VOD 수")
    parser.add_argument("--model", default="gemma2:9b", help="베이스 모델")
    parser.add_argument("--tuned-model", default=None, help="튜닝 모델 (비교용)")
    parser.add_argument("--output", default="gen_rec_sentence/data/eval_results.jsonl")
    args = parser.parse_args()

    conn = get_conn()
    try:
        contexts = fetch_vod_contexts(conn, limit=args.limit, require_embedding=True, require_poster=True)
    finally:
        conn.close()

    log.info("베이스 모델 평가: %s", args.model)
    base_eval = evaluate_model(contexts, args.model)
    log.info("  pass_rate=%.1f%% | avg_len=%.1f자", base_eval["pass_rate"] * 100, base_eval["avg_length"])

    evals = [base_eval]

    if args.tuned_model:
        log.info("튜닝 모델 평가: %s", args.tuned_model)
        tuned_eval = evaluate_model(contexts, args.tuned_model)
        log.info("  pass_rate=%.1f%% | avg_len=%.1f자", tuned_eval["pass_rate"] * 100, tuned_eval["avg_length"])
        evals.append(tuned_eval)

        log.info("\n=== 비교 결과 ===")
        log.info("  베이스 pass_rate: %.1f%% → 튜닝 pass_rate: %.1f%%", base_eval["pass_rate"] * 100, tuned_eval["pass_rate"] * 100)

    with open(args.output, "w", encoding="utf-8") as f:
        for e in evals:
            summary = {k: v for k, v in e.items() if k != "results"}
            f.write(json.dumps(summary, ensure_ascii=False) + "\n")

    log.info("평가 결과 저장 → %s", args.output)


if __name__ == "__main__":
    main()
