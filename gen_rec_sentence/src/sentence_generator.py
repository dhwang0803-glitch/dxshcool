"""Ollama 로컬 LLM 호출 → rec_sentence 생성.

베이스 모델: Gemma 2 9B (Phase 0 zero-shot 비교 결과 확정)
튜닝 후: LoRA adapter 통합 모델로 교체 예정
"""

import json
import logging

import ollama

log = logging.getLogger(__name__)

_DEFAULT_MODEL = "gemma2:9b"

_DEFAULT_PROMPT_TEMPLATE = """당신은 IPTV VOD 서비스의 감성 카피라이터입니다.
아래 VOD 정보를 바탕으로 홈 배너 포스터 하단에 표시할 감성 문구를 작성하세요.

규칙:
- 정확히 2문장 (줄바꿈 1개로 구분)
- 총 20자 이상 80자 이하 (공백 포함)
- 장면·분위기·감정을 시각적으로 묘사 — 줄거리 요약 금지
- [영상 시각 패턴]이 있으면 해당 분위기를 문구에 반드시 반영할 것
- 감독명·배우명이 한국어면 적극 활용, 영문이면 사용하지 말 것
- 제목·회차 번호를 문구 안에 반복 금지
- "~보세요", "~하세요", "~세요" 등 권유·명령형 어미 금지
- "~있습니다", "~합니다", "~됩니다" 등 합쇼체 어미 금지 — 서술형(~다/~네/~지) 또는 명사형 종결
- HTML 태그(<br> 등) 사용 금지
- JSON 형식으로만 응답: {{"rec_sentence": "..."}}

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
    """단일 VOD → rec_sentence 생성.

    Args:
        ctx: context_builder.fetch_vod_contexts()의 개별 항목
        model: Ollama 모델명
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
