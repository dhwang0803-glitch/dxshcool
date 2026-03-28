"""Phase 1: seed_examples.jsonl의 빈 rec_sentence를 gemma2:9b로 채우기.

Usage:
    python gen_rec_sentence/scripts/fill_seed_sentences.py --batch-size 30
    python gen_rec_sentence/scripts/fill_seed_sentences.py --batch-start 30 --batch-size 30
    python gen_rec_sentence/scripts/fill_seed_sentences.py --dry-run --batch-size 3
    python gen_rec_sentence/scripts/fill_seed_sentences.py --overwrite  # 기존 생성 결과 재생성
"""

import argparse
import json
import logging
import os
import re
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv

load_dotenv(".env")

from gen_rec_sentence.src.context_builder import get_conn
from gen_rec_sentence.src.quality_filter import validate
from gen_rec_sentence.src.sentence_generator import generate_sentence
from gen_rec_sentence.src.visual_extractor import VisualExtractor

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_ENGLISH_NAME_RE = re.compile(r"^[A-Z][a-z]+(\s[A-Z][a-z]+(-[a-z]+)*)+$")


def _normalize_director(name: str) -> str:
    """영문 감독명이면 빈 문자열 반환."""
    if not name:
        return ""
    if _ENGLISH_NAME_RE.match(name.strip()):
        return ""
    return name


def _fetch_full_embeddings(vod_ids: list[str]) -> dict[str, list[float]]:
    """DB에서 풀 512차원 임베딩 조회."""
    if not vod_ids:
        return {}
    try:
        conn = get_conn()
        with conn.cursor() as cur:
            placeholders = ",".join(["%s"] * len(vod_ids))
            cur.execute(
                f"SELECT vod_id_fk, embedding FROM public.vod_embedding WHERE vod_id_fk IN ({placeholders})",
                vod_ids,
            )
            rows = cur.fetchall()
        conn.close()

        result = {}
        for vod_id, emb_raw in rows:
            if emb_raw is None:
                continue
            if isinstance(emb_raw, str):
                vals = [float(x) for x in emb_raw.strip("[]").split(",") if x.strip()]
            else:
                try:
                    vals = list(emb_raw)
                except Exception:
                    vals = []
            result[vod_id] = vals
        log.info("DB 임베딩 조회: %d / %d건", len(result), len(vod_ids))
        return result
    except Exception as e:
        log.warning("임베딩 DB 조회 실패 (스킵): %s", e)
        return {}


def seed_record_to_ctx(record: dict, full_embedding: list = None) -> dict:
    """seed_examples.jsonl 레코드 → sentence_generator 입력 ctx 변환."""
    inp = record.get("input", {})
    embedding = full_embedding if full_embedding else inp.get("embedding_preview", [])
    return {
        "vod_id": record.get("vod_id", ""),
        "asset_nm": inp.get("asset_nm", ""),
        "genre": inp.get("genre", ""),
        "genre_detail": inp.get("genre_detail", ""),
        "director": _normalize_director(inp.get("director", "")),
        "cast_lead": inp.get("cast_lead", ""),
        "smry": inp.get("smry", ""),
        "rating": inp.get("rating", ""),
        "embedding": embedding,
    }


def main():
    parser = argparse.ArgumentParser(description="seed_examples rec_sentence 생성")
    parser.add_argument("--input", default="gen_rec_sentence/data/seed_examples.jsonl")
    parser.add_argument("--output", default=None, help="출력 경로 (기본: input 파일 덮어쓰기)")
    parser.add_argument("--model", default="gemma2:9b")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--dry-run", action="store_true", help="생성만 하고 저장 안 함")
    parser.add_argument("--batch-start", type=int, default=0, help="시작 인덱스 (0부터)")
    parser.add_argument("--batch-size", type=int, default=30, help="이번 배치 생성 건수 (기본 30)")
    parser.add_argument("--overwrite", action="store_true", help="기존 rec_sentence 있어도 재생성")
    parser.add_argument("--no-visual", action="store_true", help="시각 키워드 추출 비활성화")
    args = parser.parse_args()

    output_path = args.output or args.input

    # 1) 읽기
    records = []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    log.info("총 %d건 로드", len(records))

    # 배치 범위 계산
    batch_end = args.batch_start + args.batch_size
    targets = records[args.batch_start:batch_end]
    log.info("배치: [%d ~ %d) / 전체 %d건", args.batch_start, min(batch_end, len(records)), len(records))

    # 2) 배치 대상 vod_id → 풀 임베딩 일괄 조회 + VisualExtractor 초기화
    extractor = None
    embeddings_map = {}
    if not args.no_visual:
        vod_ids = [r.get("vod_id", "") for r in targets if not r.get("output", {}).get("rec_sentence") or args.overwrite]
        embeddings_map = _fetch_full_embeddings(vod_ids)
        if embeddings_map:
            extractor = VisualExtractor()
            log.info("VisualExtractor 초기화 완료")

    # 3) 생성
    passed = failed = skipped = 0
    for i, record in enumerate(targets):
        global_idx = args.batch_start + i
        current_sentence = record.get("output", {}).get("rec_sentence", "")
        if not args.overwrite and current_sentence:
            skipped += 1
            continue

        vod_id = record.get("vod_id", "")
        full_emb = embeddings_map.get(vod_id, [])
        ctx = seed_record_to_ctx(record, full_embedding=full_emb)

        # 시각 키워드 추출
        visual_keywords = []
        if extractor and full_emb:
            visual_keywords = extractor.extract(full_emb, top_k=5)
            ctx["visual_keywords"] = visual_keywords

        log.info("[%d/%d] (#%d) 생성 중: %s | 시각키워드: %s",
                 i + 1, len(targets), global_idx + 1,
                 ctx["asset_nm"],
                 ", ".join(visual_keywords) if visual_keywords else "없음")

        # 품질 실패 시 최대 2회 재시도 (temperature 높여 다양성 증가)
        quality_pass = False
        for quality_attempt in range(3):
            temp = args.temperature + quality_attempt * 0.1
            result = generate_sentence(ctx, model=args.model, temperature=temp)
            sentence = result.get("rec_sentence")

            if not sentence:
                log.error("  생성 실패 (None): %s", result.get("error"))
                failed += 1
                break

            validated = validate(result, ctx)
            if validated["pass"]:
                record["output"]["rec_sentence"] = sentence
                record["output"].pop("fail_reasons", None)
                record["model_name"] = args.model
                if visual_keywords:
                    record["visual_keywords_used"] = visual_keywords
                passed += 1
                quality_pass = True
                log.info("  ✅ (시도%d) %s", quality_attempt + 1, sentence[:70])
                break
            else:
                log.warning("  ❌ 품질 실패(시도%d) %s: %s", quality_attempt + 1, validated["fail_reasons"], sentence[:70])
                if quality_attempt == 2:
                    record["output"]["rec_sentence"] = sentence
                    record["output"]["fail_reasons"] = validated["fail_reasons"]
                    record["model_name"] = args.model
                    failed += 1

        # dry-run이면 저장 안 하고 출력만
        if args.dry_run:
            status = "✅" if (sentence and not result.get("error")) else "❌"
            print(f"\n[{global_idx+1}] {ctx['asset_nm']} {status}")
            if visual_keywords:
                print(f"  [시각] {', '.join(visual_keywords)}")
            if sentence:
                print(f"  {sentence}")
            continue

        # 5건마다 중간 저장
        if (i + 1) % 5 == 0:
            _save(records, output_path)
            log.info("  중간 저장 완료 (%d건 처리)", i + 1 - skipped)

        time.sleep(0.1)

    # 4) 최종 저장
    if not args.dry_run:
        _save(records, output_path)

    next_start = min(batch_end, len(records))
    log.info("배치 완료 — 통과: %d, 품질실패: %d, 스킵(기존): %d", passed, failed, skipped)
    log.info("다음 배치: --batch-start %d --batch-size %d", next_start, args.batch_size)
    if not args.dry_run:
        log.info("저장 경로: %s", output_path)


def _save(records: list[dict], path: str):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
