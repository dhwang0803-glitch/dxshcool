"""Phase 2: Seed 데이터 기반 LLM 증강 → training_data.jsonl 생성.

Seed 50~100건을 few-shot 예시로 활용, LLM(Ollama)으로 500~1,000건 증강.
생성 후 사람 검수 필요.

Usage:
    python gen_rec_sentence/scripts/augment_training_data.py \
        --seed gen_rec_sentence/data/seed_examples.jsonl \
        --output gen_rec_sentence/data/training_data.jsonl \
        --target 500
"""

import argparse
import json
import logging
import random
import sys
import time

sys.path.insert(0, ".")

from gen_rec_sentence.src.context_builder import fetch_vod_contexts, get_conn
from gen_rec_sentence.src.quality_filter import validate

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def load_seed(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(l) for l in f if json.loads(l).get("output", {}).get("rec_sentence")]


def build_few_shot_prompt(seed_examples: list[dict], target_ctx: dict, n_shots: int = 3) -> str:
    shots = random.sample(seed_examples, min(n_shots, len(seed_examples)))
    examples = ""
    for s in shots:
        inp = s["input"]
        examples += f"""
예시:
제목: {inp['asset_nm']} | 장르: {inp['genre']} | 감독: {inp['director']}
줄거리: {inp['smry'][:150]}
→ {s['output']['rec_sentence']}
"""
    return f"""아래 예시를 참고하여 새 VOD의 감성 문구를 생성하세요. JSON만 응답하세요.
{examples}
새 VOD:
제목: {target_ctx['asset_nm']} | 장르: {target_ctx['genre']} | 감독: {target_ctx['director']}
줄거리: {target_ctx['smry'][:150]}

응답: {{"rec_sentence": "..."}}"""


def main():
    import ollama

    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", default="gen_rec_sentence/data/seed_examples.jsonl")
    parser.add_argument("--output", default="gen_rec_sentence/data/training_data.jsonl")
    parser.add_argument("--target", type=int, default=500)
    parser.add_argument("--model", default="gemma2:9b")
    args = parser.parse_args()

    seed = load_seed(args.seed)
    log.info("Seed 로드: %d건", len(seed))

    conn = get_conn()
    try:
        contexts = fetch_vod_contexts(conn, limit=args.target * 2, require_embedding=True, require_poster=True)
    finally:
        conn.close()

    random.shuffle(contexts)
    generated = []

    for ctx in contexts:
        if len(generated) >= args.target:
            break
        prompt = build_few_shot_prompt(seed, ctx)
        try:
            resp = ollama.chat(model=args.model, messages=[{"role": "user", "content": prompt}])
            content = resp["message"]["content"]
            start, end = content.find("{"), content.rfind("}") + 1
            parsed = json.loads(content[start:end])
            sentence = parsed.get("rec_sentence", "")
            if not sentence:
                continue
            result = validate({"vod_id": ctx["vod_id"], "rec_sentence": sentence, "model_name": args.model, "embedding_used": False}, ctx)
            if not result["pass"]:
                log.debug("품질 실패: %s | %s", ctx["vod_id"], result["fail_reasons"])
                continue
            record = {
                "instruction": "VOD의 메타데이터와 시각 키워드를 바탕으로 포스터 하단에 표시할 감성 문구를 생성하세요.",
                "input": {
                    "asset_nm": ctx["asset_nm"],
                    "genre": ctx["genre"],
                    "director": ctx["director"],
                    "smry": ctx["smry"][:300],
                    "embedding": ctx["embedding"][:10],
                },
                "output": {"rec_sentence": sentence},
                "vod_id": ctx["vod_id"],
                "augmented": True,
            }
            generated.append(record)
            if len(generated) % 50 == 0:
                log.info("증강 진행: %d/%d", len(generated), args.target)
        except Exception as e:
            log.warning("생성 실패: %s | %s", ctx["vod_id"], e)
        time.sleep(0.1)

    with open(args.output, "w", encoding="utf-8") as f:
        for r in generated:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    log.info("증강 완료: %d건 → %s (사람 검수 필요)", len(generated), args.output)


if __name__ == "__main__":
    main()
