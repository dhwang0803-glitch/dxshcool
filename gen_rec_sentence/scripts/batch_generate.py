"""세그먼트별 rec_sentence 배치 생성.

온라인 모드 (DB 직접 접속):
    python gen_rec_sentence/scripts/batch_generate.py
    python gen_rec_sentence/scripts/batch_generate.py --limit 100 --dry-run

오프라인 모드 (Colab — parquet 기반, DB 불필요):
    python gen_rec_sentence/scripts/batch_generate.py \
        --offline gen_rec_sentence/data/colab_data

    vLLM 백엔드 (Colab A100 — 병렬 처리):
    python gen_rec_sentence/scripts/batch_generate.py \
        --offline gen_rec_sentence/data/colab_data \
        --backend vllm --model google/gemma-2-27b-it \
        --concurrency 16

    결과: {offline_dir}/results.parquet
    로컬에서 ingest_results.py로 DB 적재
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ollama는 --backend ollama일 때만 import (vllm 모드에서 불필요)
_ollama = None

_N_SEGMENTS = 5
_SAVE_EVERY = 200
_MIN_LEN = 20

# ── 세그먼트 페르소나 ───────────────────────────────────────────────────────────
_SEGMENT_PERSONAS = {
    0: "어린이와 함께 시청하는 키즈/애니 팬. 밝고 경쾌한 톤, 모험·신비·우정·성장을 강조.",
    1: "버라이어티·예능을 즐기는 시청자. 유머·공감·에너지·반전 포인트를 강조.",
    2: "액션·범죄·장르물을 즐기는 성인 시청자. 긴장감·아드레날린·반전·날카로운 서사를 강조.",
    3: "가족 단위 시청자. 감동·따뜻함·공감·세대 간 유대를 강조.",
    4: "드라마 감성을 즐기는 주류 시청자. 감정선·캐릭터·관계·몰입감을 강조.",
}
_SAFE_RATINGS = {"전체가", "7세", "7세이상", "전체", "전체관람가", "전체 관람가"}

_PROMPT_TEMPLATE = """\
당신은 IPTV VOD 콘텐츠 소개 작가입니다.
아래 VOD 정보를 바탕으로 홈 배너 포스터 하단에 표시할 소개 문구를 작성하세요.

목표: 문구만 읽고도 "이 VOD가 어떤 내용인지" 즉시 파악할 수 있어야 한다.
고객이 시청 여부를 바로 결정할 수 있도록 핵심 배경·상황·갈등을 구체적으로 압축한다.

규칙:
- 반드시 50자 내외로 작성 (공백 포함, 절대 80자 초과 금지). 1~2문장, 최소 20자
- 핵심 배경·상황·갈등을 구체적으로 전달 — 시적·추상적 표현 금지
- [타겟 시청자]의 취향과 감성 포인트에 맞춰 문구의 톤과 강조점을 조절할 것
- 감독명·배우명 중 네임밸류가 있으면 적극 활용 (영문명은 제외)
- 느낌표(!) 최대 1개 — 남발 금지
- 제목·회차 번호를 문구 안에 반복 금지
- "~보세요/~하세요" 권유형, "~합니다" 합쇼체 금지 — 서술형(~다/~네) 또는 명사형 종결
- "기대된다" 같은 시청자 평 금지 — 소개문이지 리뷰가 아니다
- 한글 문장 중간에 영어 단어를 섞지 말 것 (고유명사·약어는 허용)
- 줄임표(...)로 끝낼 경우 "마주한 진실은..."처럼 방향성 있게. "만난 후..."처럼 허공에 뜬 채 끝내지 말 것
- 첫 문장에서 흥미를 유발했으면, 둘째 문장은 핵심 정보를 깔끔하게 전달
- HTML 태그 금지
- JSON 형식으로만 응답: {{"rec_sentence": "..."}}

VOD 정보:
- 제목: {asset_nm}
- 장르: {genre_detail}
- 감독: {director}
- 출연: {cast_lead}
- 줄거리: {smry}

타겟 시청자: {persona}
"""


# ── 프롬프트 조립 ─────────────────────────────────────────────────────────────

def _build_prompt(ctx: dict, segment_id: int) -> str:
    rating = ctx.get("rating", "")
    if any(r in rating for r in _SAFE_RATINGS):
        persona = "전 연령 가족 시청자. 밝고 따뜻한 톤 유지."
    else:
        persona = _SEGMENT_PERSONAS.get(segment_id, "일반 시청자.")

    return _PROMPT_TEMPLATE.format(
        asset_nm=ctx["asset_nm"],
        genre_detail=ctx["genre_detail"],
        director=ctx["director"],
        cast_lead=ctx["cast_lead"],
        smry=ctx["smry"][:300],
        persona=persona,
    )


def _trim_to_limit(sentence: str, limit: int = 80) -> str:
    """80자 초과 시 첫 문장만 사용. 그래도 초과면 마지막 구두점에서 자름."""
    if len(sentence) <= limit:
        return sentence
    # 첫 문장 추출 (. ! ? 기준)
    m = re.match(r"^(.+?[.!?다네])\s", sentence)
    if m and _MIN_LEN <= len(m.group(1)) <= limit:
        return m.group(1)
    # 그래도 안 되면 limit 이내 마지막 구두점/쉼표에서 자름
    truncated = sentence[:limit]
    for i in range(len(truncated) - 1, _MIN_LEN - 1, -1):
        if truncated[i] in ".!?다네":
            return truncated[:i + 1]
    return truncated


def _call_ollama(prompt: str, model: str, temperature: float) -> str | None:
    from gen_rec_sentence.src.sentence_generator import _parse_json_response
    global _ollama
    if _ollama is None:
        import ollama as _ol
        _ollama = _ol
    for attempt in range(3):
        try:
            response = _ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature + attempt * 0.1},
            )
            parsed = _parse_json_response(response["message"]["content"].strip())
            sentence = parsed.get("rec_sentence")
            if sentence:
                return _trim_to_limit(sentence)
            return None
        except Exception as e:
            log.warning("  ollama 실패 (시도 %d): %s", attempt + 1, e)
    return None


# ── vLLM 비동기 호출 ─────────────────────────────────────────────────────────

async def _call_vllm(
    session: "aiohttp.ClientSession",
    prompt: str,
    model: str,
    temperature: float,
    base_url: str = "http://localhost:8000",
) -> str | None:
    """vLLM OpenAI-compatible API 비동기 호출."""
    from gen_rec_sentence.src.sentence_generator import _parse_json_response

    url = f"{base_url}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": 256,
    }
    for attempt in range(3):
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    log.warning("  vLLM HTTP %d (시도 %d)", resp.status, attempt + 1)
                    continue
                data = await resp.json()
            content = data["choices"][0]["message"]["content"].strip()
            parsed = _parse_json_response(content)
            sentence = parsed.get("rec_sentence")
            if sentence:
                return _trim_to_limit(sentence)
            return None
        except Exception as e:
            log.warning("  vLLM 실패 (시도 %d): %s", attempt + 1, e)
    return None


async def _process_one_vllm(
    session: "aiohttp.ClientSession",
    semaphore: asyncio.Semaphore,
    vod_id: str,
    seg_id: int,
    ctx: dict,
    model: str,
    base_temperature: float,
    validate_fn,
    base_url: str,
) -> dict | None:
    """단일 (vod_id, segment_id) 쌍을 vLLM으로 처리 (재시도 포함)."""
    _MAX_RETRIES = 5
    async with semaphore:
        for retry in range(_MAX_RETRIES):
            temp = base_temperature + retry * 0.1
            sentence = await _call_vllm(
                session, _build_prompt(ctx, seg_id), model, temp, base_url,
            )
            if sentence is None:
                continue
            validated = validate_fn(
                {"vod_id": vod_id, "rec_sentence": sentence}, ctx,
            )
            if validated["pass"]:
                return {
                    "vod_id": vod_id,
                    "segment_id": seg_id,
                    "rec_sentence": sentence,
                    "model_name": model,
                }
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  온라인 모드 (DB 직접 접속)
# ══════════════════════════════════════════════════════════════════════════════

def _run_online(args) -> None:
    import psycopg2.extras
    from dotenv import load_dotenv
    load_dotenv(".env")
    from gen_rec_sentence.src.context_builder import get_conn, fetch_vod_contexts_by_ids
    from gen_rec_sentence.src.quality_filter import validate

    conn = get_conn()
    try:
        # Step 1: 추천 풀
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT vod_id_fk FROM (
                    SELECT vod_id_fk FROM serving.hybrid_recommendation
                    UNION
                    SELECT vod_id_fk FROM serving.popular_by_age
                ) t
            """)
            pool_vods = [r[0] for r in cur.fetchall()]
        log.info("[1/4] 추천 풀 VOD: %d건", len(pool_vods))

        if args.limit:
            pool_vods = pool_vods[:args.limit]
            log.info("  --limit %d 적용", args.limit)

        # Step 2: 기존 쌍 제외
        with conn.cursor() as cur:
            cur.execute(
                "SELECT vod_id_fk, segment_id FROM serving.rec_sentence WHERE vod_id_fk = ANY(%s)",
                (pool_vods,),
            )
            existing = {(r[0], r[1]) for r in cur.fetchall()}

        todo = [(v, s) for v in pool_vods for s in range(_N_SEGMENTS) if (v, s) not in existing]
        log.info("[2/4] 생성 대상: %d쌍 (기존 %d쌍 스킵)", len(todo), len(existing))

        if not todo or args.dry_run:
            log.info("DRY-RUN 또는 대상 없음. 종료.")
            return

        # Step 3: 컨텍스트 조회
        todo_vod_ids = list({v for v, _ in todo})
        contexts = fetch_vod_contexts_by_ids(conn, todo_vod_ids)
        ctx_map = {c["vod_id"]: c for c in contexts}
        log.info("[3/4] VOD 컨텍스트 로드: %d건", len(ctx_map))

        # Step 4: 생성 + UPSERT
        log.info("[4/4] 문구 생성 시작 (총 %d쌍)...", len(todo))
        upsert_queue, total_ok, total_fail = [], 0, 0
        failed_log = "gen_rec_sentence/data/batch_failed.jsonl"

        _MAX_RETRIES = 5

        for i, (vod_id, seg_id) in enumerate(todo):
            ctx = ctx_map.get(vod_id)
            if ctx is None:
                continue

            success = False
            for retry in range(_MAX_RETRIES):
                temp = args.temperature + retry * 0.1
                sentence = _call_ollama(_build_prompt(ctx, seg_id), args.model, temp)
                if sentence is None:
                    continue

                validated = validate({"vod_id": vod_id, "rec_sentence": sentence}, ctx)
                if validated["pass"]:
                    upsert_queue.append({"vod_id": vod_id, "segment_id": seg_id,
                                         "rec_sentence": sentence, "model_name": args.model})
                    total_ok += 1
                    success = True
                    break

            if not success:
                total_fail += 1
                with open(failed_log, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"vod_id": vod_id, "segment_id": seg_id}, ensure_ascii=False) + "\n")

            if len(upsert_queue) >= _SAVE_EVERY:
                _upsert_batch(conn, upsert_queue)
                log.info("  진행: %d/%d | 성공 %d / 실패 %d", i + 1, len(todo), total_ok, total_fail)
                upsert_queue.clear()

        if upsert_queue:
            _upsert_batch(conn, upsert_queue)

        log.info("완료 — 성공: %d쌍 | 실패: %d쌍", total_ok, total_fail)
    finally:
        conn.close()


def _upsert_batch(conn, rows):
    import psycopg2.extras
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO serving.rec_sentence (vod_id_fk, segment_id, rec_sentence, model_name)
            VALUES %s
            ON CONFLICT (vod_id_fk, segment_id) DO UPDATE SET
                rec_sentence = EXCLUDED.rec_sentence,
                model_name   = EXCLUDED.model_name,
                generated_at = NOW()
            """,
            [(r["vod_id"], r["segment_id"], r["rec_sentence"], r["model_name"]) for r in rows],
        )
    conn.commit()


# ══════════════════════════════════════════════════════════════════════════════
#  오프라인 모드 (Colab — parquet 기반)
# ══════════════════════════════════════════════════════════════════════════════

def _run_offline(args) -> None:
    import pandas as pd
    from gen_rec_sentence.src.quality_filter import validate

    offline_dir = args.offline
    ctx_path = os.path.join(offline_dir, "vod_contexts.parquet")
    exist_path = os.path.join(offline_dir, "existing_pairs.parquet")
    result_path = os.path.join(offline_dir, "results.parquet")

    # Step 1: VOD 컨텍스트 로드
    df_ctx = pd.read_parquet(ctx_path)
    log.info("[1/4] VOD 컨텍스트 로드: %d건 (%s)", len(df_ctx), ctx_path)

    if args.limit:
        df_ctx = df_ctx.head(args.limit)
        log.info("  --limit %d 적용", args.limit)

    ctx_map = {}
    for _, row in df_ctx.iterrows():
        ctx_map[row["vod_id"]] = {col: str(row[col]) for col in df_ctx.columns}

    # Step 2: 기존 쌍 + 이미 생성된 결과 제외
    existing = set()
    if os.path.exists(exist_path):
        df_exist = pd.read_parquet(exist_path)
        existing = {(r["vod_id"], int(r["segment_id"])) for _, r in df_exist.iterrows()}
        log.info("  DB 기존 쌍: %d건", len(existing))

    # 이전 실행 결과 이어받기 (resume)
    done_rows = []
    if os.path.exists(result_path):
        df_done = pd.read_parquet(result_path)
        done_rows = df_done.to_dict("records")
        for r in done_rows:
            existing.add((r["vod_id"], int(r["segment_id"])))
        log.info("  이전 결과 이어받기: %d건", len(done_rows))

    todo = [(v, s) for v in ctx_map for s in range(_N_SEGMENTS) if (v, s) not in existing]
    log.info("[2/4] 생성 대상: %d쌍 (기존 %d쌍 스킵)", len(todo), len(existing))

    if not todo or args.dry_run:
        log.info("DRY-RUN 또는 대상 없음. 종료.")
        return

    log.info("[3/4] 모델: %s / temperature: %.1f / backend: %s",
             args.model, args.temperature, args.backend)

    # Step 4: 백엔드에 따라 분기
    if args.backend == "vllm":
        _run_offline_vllm(args, todo, ctx_map, done_rows, result_path, validate)
    else:
        _run_offline_ollama(args, todo, ctx_map, done_rows, result_path, validate)


def _run_offline_ollama(args, todo, ctx_map, done_rows, result_path, validate) -> None:
    """기존 Ollama 순차 처리 (로컬용)."""
    log.info("[4/4] Ollama 순차 생성 시작 (총 %d쌍)...", len(todo))
    new_rows = []
    total_ok = total_fail = 0
    _MAX_RETRIES = 5

    for i, (vod_id, seg_id) in enumerate(todo):
        ctx = ctx_map.get(vod_id)
        if ctx is None:
            continue

        success = False
        for retry in range(_MAX_RETRIES):
            temp = args.temperature + retry * 0.1
            sentence = _call_ollama(_build_prompt(ctx, seg_id), args.model, temp)
            if sentence is None:
                continue

            validated = validate({"vod_id": vod_id, "rec_sentence": sentence}, ctx)
            if validated["pass"]:
                new_rows.append({
                    "vod_id": vod_id,
                    "segment_id": seg_id,
                    "rec_sentence": sentence,
                    "model_name": args.model,
                })
                total_ok += 1
                success = True
                break

        if not success:
            total_fail += 1

        if (total_ok + total_fail) % _SAVE_EVERY == 0 and new_rows:
            _save_results(result_path, done_rows + new_rows)
            log.info("  진행: %d/%d | 성공 %d / 실패 %d | 저장 완료",
                     i + 1, len(todo), total_ok, total_fail)

    _save_results(result_path, done_rows + new_rows)
    log.info("완료 — 성공: %d쌍 | 실패: %d쌍", total_ok, total_fail)
    log.info("결과: %s (%d건)", result_path, len(done_rows) + len(new_rows))


def _run_offline_vllm(args, todo, ctx_map, done_rows, result_path, validate) -> None:
    """vLLM 비동기 병렬 처리 (Colab A100용)."""
    import aiohttp

    # aiohttp / urllib3 등의 HTTP 요청 로그 억제 (Colab 브라우저 부하 방지)
    for noisy in ("aiohttp", "urllib3", "httpcore", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    concurrency = getattr(args, "concurrency", 16)
    base_url = getattr(args, "vllm_url", "http://localhost:8000")
    log.info("[4/4] vLLM 병렬 생성 시작 (총 %d쌍, 동시 %d개)...", len(todo), concurrency)

    new_rows = []
    total_ok = 0
    total_fail = 0
    t_start = time.time()

    async def _run_batch(batch):
        """batch 단위 비동기 실행."""
        sem = asyncio.Semaphore(concurrency)
        conn = aiohttp.TCPConnector(limit=concurrency + 4)
        async with aiohttp.ClientSession(connector=conn) as session:
            tasks = []
            for vod_id, seg_id in batch:
                ctx = ctx_map.get(vod_id)
                if ctx is None:
                    continue
                tasks.append(
                    _process_one_vllm(
                        session, sem, vod_id, seg_id, ctx,
                        args.model, args.temperature, validate, base_url,
                    )
                )
            return await asyncio.gather(*tasks)

    # _SAVE_EVERY 단위로 배치 실행 + 중간 저장
    _LOG_EVERY = 1000  # 로그는 1000건마다 (Colab 출력 부하 방지)
    _last_log_count = 0

    for batch_start in range(0, len(todo), _SAVE_EVERY):
        batch = todo[batch_start : batch_start + _SAVE_EVERY]
        results = asyncio.run(_run_batch(batch))

        for r in results:
            if r is not None:
                new_rows.append(r)
                total_ok += 1
            else:
                total_fail += 1

        _save_results(result_path, done_rows + new_rows)

        # 로그는 _LOG_EVERY 단위로만 출력
        processed = total_ok + total_fail
        if processed - _last_log_count >= _LOG_EVERY or batch_start + len(batch) >= len(todo):
            elapsed = time.time() - t_start
            speed = processed / elapsed if elapsed > 0 else 0
            eta_min = (len(todo) - batch_start - len(batch)) / speed / 60 if speed > 0 else 0
            log.info(
                "  진행: %d/%d (%.0f%%) | 성공 %d / 실패 %d | %.1f건/초 | ETA %.0f분",
                batch_start + len(batch), len(todo),
                (batch_start + len(batch)) / len(todo) * 100,
                total_ok, total_fail, speed, eta_min,
            )
            _last_log_count = processed

    elapsed = time.time() - t_start
    log.info("완료 — 성공: %d쌍 | 실패: %d쌍 | 소요: %.0f초 (%.1f건/초)",
             total_ok, total_fail, elapsed,
             (total_ok + total_fail) / elapsed if elapsed > 0 else 0)
    log.info("결과: %s (%d건)", result_path, len(done_rows) + len(new_rows))


def _save_results(path: str, rows: list[dict]) -> None:
    import pandas as pd
    df = pd.DataFrame(rows)
    df.to_parquet(path, index=False)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="세그먼트별 rec_sentence 배치 생성")
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 VOD 수")
    parser.add_argument("--model", default="gemma3:12b-it-qat")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 대상 건수만 확인")
    parser.add_argument("--offline", type=str, default=None,
                        help="오프라인 모드: parquet 디렉토리 경로 (Colab용, DB 불필요)")
    parser.add_argument("--backend", choices=["ollama", "vllm"], default="ollama",
                        help="LLM 백엔드 (default: ollama)")
    parser.add_argument("--concurrency", type=int, default=16,
                        help="vLLM 동시 요청 수 (default: 16)")
    parser.add_argument("--vllm-url", default="http://localhost:8000",
                        help="vLLM 서버 URL (default: http://localhost:8000)")
    args = parser.parse_args()

    if args.offline:
        _run_offline(args)
    else:
        _run_online(args)


if __name__ == "__main__":
    main()
