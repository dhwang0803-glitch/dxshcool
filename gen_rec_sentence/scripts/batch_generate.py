"""세그먼트별 rec_sentence 배치 생성 → serving.rec_sentence 적재.

실행 대상:
  - serving.hybrid_recommendation 의 DISTINCT VOD (개인화 추천 풀)
  - serving.popular_by_age 의 DISTINCT VOD (콜드스타트 fallback 풀)

증분 실행:
  - (vod_id_fk, segment_id) 쌍이 이미 serving.rec_sentence에 있으면 스킵
  - 추천 풀 갱신 시 이 스크립트를 재실행하면 신규 VOD만 처리

Usage:
    python gen_rec_sentence/scripts/batch_generate.py
    python gen_rec_sentence/scripts/batch_generate.py --limit 100 --dry-run
    python gen_rec_sentence/scripts/batch_generate.py --model gemma2:9b --temperature 0.7
"""

import argparse
import json
import logging
import sys

import psycopg2.extras

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, ".")

from dotenv import load_dotenv
load_dotenv(".env")

from gen_rec_sentence.src.context_builder import get_conn, fetch_vod_contexts_by_ids
from gen_rec_sentence.src.quality_filter import validate
from gen_rec_sentence.src.visual_extractor import VisualExtractor
import ollama

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

_N_SEGMENTS = 5
_UPSERT_BATCH = 200
_FAILED_LOG = "gen_rec_sentence/data/batch_failed.jsonl"

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
당신은 IPTV VOD 서비스의 감성 카피라이터입니다.
아래 VOD 정보를 바탕으로 홈 배너 포스터 하단에 표시할 감성 문구를 작성하세요.

규칙:
- 정확히 2문장 (줄바꿈 1개로 구분)
- 총 20자 이상 80자 이하 (공백 포함)
- 장면·분위기·감정을 시각적으로 묘사 — 줄거리 요약 금지
- [영상 시각 패턴]이 있으면 해당 분위기를 문구에 반드시 반영할 것
- [타겟 시청자]의 취향과 감성 포인트에 맞춰 문구의 톤과 강조점을 조절할 것
- 감독명·배우명이 한국어면 적극 활용, 영문이면 사용하지 말 것
- 제목·회차 번호를 문구 안에 반복 금지
- "~보세요", "~하세요", "~봐요", "~봐" 등 권유·명령형 어미 금지
- "~니다", "~습니다" 등 합쇼체 어미 금지 — 서술형(~다/~네/~지) 또는 명사형 종결
- 아래 단어 사용 금지 (클리셰): 어둠, 불꽃, 용기, 마법, 펼쳐지다, 선사하다
- HTML 태그(<br> 등) 사용 금지
- JSON 형식으로만 응답: {{"rec_sentence": "..."}}

VOD 정보:
- 제목: {asset_nm}
- 장르: {genre_detail}
- 감독: {director}
- 출연: {cast_lead}
- 줄거리: {smry}
- 영상 시각 패턴: {visual_keywords}

타겟 시청자: {persona}
"""


# ── 추천 풀 조회 ───────────────────────────────────────────────────────────────

def fetch_recommendation_pool(conn) -> list[str]:
    """추천 풀 = hybrid_recommendation ∪ popular_by_age (DISTINCT vod_id_fk)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT DISTINCT vod_id_fk FROM (
                SELECT vod_id_fk FROM serving.hybrid_recommendation
                UNION
                SELECT vod_id_fk FROM serving.popular_by_age
            ) t
            """
        )
        return [r[0] for r in cur.fetchall()]


# ── 이미 생성된 (vod_id, segment_id) 쌍 조회 ─────────────────────────────────

def fetch_existing_pairs(conn, vod_ids: list[str]) -> set[tuple[str, int]]:
    """serving.rec_sentence에 이미 있는 (vod_id_fk, segment_id) 쌍."""
    if not vod_ids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT vod_id_fk, segment_id FROM serving.rec_sentence WHERE vod_id_fk = ANY(%s)",
            (vod_ids,),
        )
        return {(r[0], r[1]) for r in cur.fetchall()}


# ── 문구 생성 ──────────────────────────────────────────────────────────────────

def _build_prompt(ctx: dict, segment_id: int, visual_keywords: list[str]) -> str:
    rating = ctx.get("rating", "")
    if any(r in rating for r in _SAFE_RATINGS):
        persona = "전 연령 가족 시청자. 밝고 따뜻한 톤 유지."
    else:
        persona = _SEGMENT_PERSONAS.get(segment_id, "일반 시청자.")

    visual_str = ", ".join(visual_keywords) if visual_keywords else "정보 없음"
    return _PROMPT_TEMPLATE.format(
        asset_nm=ctx["asset_nm"],
        genre_detail=ctx["genre_detail"],
        director=ctx["director"],
        cast_lead=ctx["cast_lead"],
        smry=ctx["smry"][:300],
        visual_keywords=visual_str,
        persona=persona,
    )


def _call_ollama(prompt: str, model: str, temperature: float) -> str | None:
    from gen_rec_sentence.src.sentence_generator import _parse_json_response
    for attempt in range(3):
        try:
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature + attempt * 0.1},
            )
            parsed = _parse_json_response(response["message"]["content"].strip())
            return parsed.get("rec_sentence")
        except Exception as e:
            log.warning("  ollama 실패 (시도 %d): %s", attempt + 1, e)
    return None


# ── UPSERT ─────────────────────────────────────────────────────────────────────

def upsert_batch(conn, rows: list[dict]) -> int:
    """rows: [{"vod_id", "segment_id", "rec_sentence", "model_name"}, ...]"""
    if not rows:
        return 0
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
    return len(rows)


# ── main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="세그먼트별 rec_sentence 배치 생성")
    parser.add_argument("--limit", type=int, default=None, help="처리할 최대 VOD 수")
    parser.add_argument("--model", default="gemma2:9b")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 대상 건수만 확인")
    args = parser.parse_args()

    conn = get_conn()
    try:
        # ── Step 1: 추천 풀 VOD 목록 ─────────────────────────────────────────
        pool_vods = fetch_recommendation_pool(conn)
        log.info("[1/4] 추천 풀 VOD: %d건", len(pool_vods))

        if args.limit:
            pool_vods = pool_vods[: args.limit]
            log.info("  --limit %d 적용", args.limit)

        # ── Step 2: 이미 생성된 쌍 제외 (diff) ──────────────────────────────
        existing = fetch_existing_pairs(conn, pool_vods)
        todo: list[tuple[str, int]] = [
            (vod_id, seg_id)
            for vod_id in pool_vods
            for seg_id in range(_N_SEGMENTS)
            if (vod_id, seg_id) not in existing
        ]
        log.info("[2/4] 생성 대상: %d쌍 (기존 %d쌍 스킵)", len(todo), len(existing))

        if not todo or args.dry_run:
            log.info("DRY-RUN 또는 대상 없음. 종료.")
            return

        # ── Step 3: VOD 컨텍스트 조회 ────────────────────────────────────────
        todo_vod_ids = list({vod_id for vod_id, _ in todo})
        contexts = fetch_vod_contexts_by_ids(conn, todo_vod_ids)
        ctx_map = {c["vod_id"]: c for c in contexts}
        log.info("[3/4] VOD 컨텍스트 로드: %d건", len(ctx_map))

        extractor = VisualExtractor()

        # ── Step 4: 세그먼트별 문구 생성 + UPSERT ────────────────────────────
        log.info("[4/4] 문구 생성 시작 (총 %d쌍)...", len(todo))
        upsert_queue: list[dict] = []
        total_ok = total_fail = 0

        for i, (vod_id, seg_id) in enumerate(todo):
            ctx = ctx_map.get(vod_id)
            if ctx is None:
                continue  # smry 없거나 임베딩 없는 VOD

            visual_kws = extractor.extract(ctx["embedding"], top_k=5) if ctx["embedding"] else []
            prompt = _build_prompt(ctx, seg_id, visual_kws)
            sentence = _call_ollama(prompt, model=args.model, temperature=args.temperature)

            if sentence is None:
                total_fail += 1
                with open(_FAILED_LOG, "a", encoding="utf-8") as f:
                    f.write(json.dumps({"vod_id": vod_id, "segment_id": seg_id}, ensure_ascii=False) + "\n")
                continue

            # 품질 검증
            validated = validate({"vod_id": vod_id, "rec_sentence": sentence}, ctx)
            if not validated["pass"]:
                log.debug("  품질 실패 (vod=%s seg=%d): %s", vod_id[:8], seg_id, validated["fail_reasons"])
                total_fail += 1
                continue

            upsert_queue.append({"vod_id": vod_id, "segment_id": seg_id,
                                  "rec_sentence": sentence, "model_name": args.model})
            total_ok += 1

            if len(upsert_queue) >= _UPSERT_BATCH:
                upsert_batch(conn, upsert_queue)
                log.info("  진행: %d/%d | 성공 %d / 실패 %d", i + 1, len(todo), total_ok, total_fail)
                upsert_queue.clear()

        # 잔여 flush
        if upsert_queue:
            upsert_batch(conn, upsert_queue)

        log.info("완료 — 성공: %d쌍 | 실패: %d쌍", total_ok, total_fail)
        if total_fail:
            log.info("  실패 목록: %s", _FAILED_LOG)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
