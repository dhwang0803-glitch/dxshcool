"""Ollama 로컬 LLM 호출 → rec_sentence 생성.

베이스 모델: Gemma 2 9B (Phase 0 zero-shot 비교 결과 확정)
튜닝 후: LoRA adapter 통합 모델로 교체 예정
"""

import json
import logging

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemma3:12b-it-qat"

_DEFAULT_PROMPT_TEMPLATE = """당신은 IPTV VOD 콘텐츠 소개 작가입니다.
아래 VOD 정보를 바탕으로 홈 배너 포스터 하단에 표시할 소개 문구를 작성하세요.
문구만 읽고도 "이 VOD가 어떤 내용인지" 즉시 파악할 수 있어야 한다.

규칙:
- 1~2문장, 20~80자 (공백 포함) — 반드시 지킬 것
- 핵심 배경·상황·갈등을 구체적으로 — 시적·추상적 표현 금지
- 감독명·배우명 네임밸류 있으면 활용 (영문명 제외)
- 느낌표(!) 최대 1개 — 남발 금지
- 제목 반복 금지, 권유형/합쇼체 금지
- JSON: {{"rec_sentence": "..."}}

좋은 예:
- "싸움에 재능이 있는 윤가민, 최악의 학원에서 피 튀기는 입시 대결!"
- "불법 총기로 인한 대한민국 전역의 혼돈, 정의로운 경찰이 의문의 파트너와 함께 위기를 헤쳐나간다"

나쁜 예:
- "파란 하늘 아래 펼쳐진 풍경 속, 그들의 슬픔이 새롭게 시작되는 순간" ← 무슨 VOD인지 알 수 없음

VOD 정보:
- 제목: {asset_nm}
- 장르: {genre_detail}
- 감독: {director}
- 출연: {cast_lead}
- 줄거리: {smry}
- 영상 시각 패턴: {visual_keywords}
"""

def generate_sentence(
    ctx: dict,
    model: str = _DEFAULT_MODEL,
    prompt_template: str = _DEFAULT_PROMPT_TEMPLATE,
    temperature: float = 0.7,
    max_retries: int = 2,
) -> dict:
    """단일 VOD → rec_sentence 생성 (seed data 전용).

    프로덕션 배치(batch_generate.py)는 segment_id 기반 페르소나를 직접 주입하므로
    이 함수를 사용하지 않는다.

    Args:
        ctx: context_builder.fetch_vod_contexts()의 개별 항목
        model: Ollama 모델명
        prompt_template: 기본값 _DEFAULT_PROMPT_TEMPLATE
        temperature: 생성 다양성 (0.0~1.0)
        max_retries: JSON 파싱 실패 시 재시도 횟수

    Returns:
        {"vod_id": ..., "rec_sentence": ..., "model_name": ..., "embedding_used": bool}
    """
    visual_kws = ctx.get("visual_keywords", [])
    visual_keywords_str = ", ".join(visual_kws) if visual_kws else "정보 없음"

    prompt = prompt_template.format(
        asset_nm=ctx.get("asset_nm", ""),
        genre=ctx.get("genre", ""),
        genre_detail=ctx.get("genre_detail", ""),
        director=ctx.get("director", ""),
        cast_lead=ctx.get("cast_lead", ""),
        smry=ctx.get("smry", "")[:300],
        rating=ctx.get("rating", ""),
        visual_keywords=visual_keywords_str,
    )

    for attempt in range(max_retries + 1):
        try:
            import ollama
            response = ollama.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": temperature},
            )
            content = response["message"]["content"].strip()
            parsed = _parse_json_response(content)
            return {
                "vod_id": ctx["vod_id"],
                "rec_sentence": parsed["rec_sentence"],
                "model_name": model,
                "embedding_used": bool(ctx.get("embedding")),
            }
        except (json.JSONDecodeError, KeyError) as e:
            log.warning("JSON 파싱 실패 (시도 %d/%d): %s | vod_id=%s", attempt + 1, max_retries + 1, e, ctx.get("vod_id"))
            if attempt == max_retries:
                return {"vod_id": ctx["vod_id"], "rec_sentence": None, "model_name": model, "embedding_used": False, "error": str(e)}
        except Exception as e:
            log.error("Ollama 호출 실패: %s | vod_id=%s", e, ctx.get("vod_id"))
            return {"vod_id": ctx["vod_id"], "rec_sentence": None, "model_name": model, "embedding_used": False, "error": str(e)}


def _parse_json_response(content: str) -> dict:
    """LLM 응답에서 JSON 추출 (마크다운 코드블록 제거 포함)."""
    # ```json ... ``` 블록 제거
    if "```" in content:
        lines = content.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        content = "\n".join(lines)
    # 첫 번째 { ~ } 추출
    start = content.find("{")
    end = content.rfind("}") + 1
    if start == -1 or end == 0:
        raise json.JSONDecodeError("JSON 블록 없음", content, 0)
    return json.loads(content[start:end])
