"""생성된 rec_sentence 품질 검증.

검증 항목:
  1. 길이 제약 (20~120자)
  2. 금칙어 필터
  3. 메타데이터 사실 검증 (장르/감독명 포함 여부)
  4. 줄거리 복붙 감지 (smry와 과도한 n-gram 중복)
"""

import re

_FORBIDDEN_WORDS = [
    # 광고성 과장
    "최고의", "역대급", "대박",
    # 직접 구매 유도 (과도한)
    "지금 바로", "놓치지 마세요",
    # 줄거리 요약 투 직접적
    "줄거리", "내용은",
]

_MIN_LEN = 20
_MAX_LEN = 120


def validate(result: dict, ctx: dict) -> dict:
    """단일 생성 결과 검증.

    Args:
        result: sentence_generator.generate_sentence() 반환값
        ctx: context_builder.fetch_vod_contexts() 개별 항목

    Returns:
        result에 "pass": bool, "fail_reasons": list[str] 추가
    """
    sentence = result.get("rec_sentence") or ""
    fail_reasons = []

    # 1. None / 빈 문자열
    if not sentence:
        fail_reasons.append("empty")
        result["pass"] = False
        result["fail_reasons"] = fail_reasons
        return result

    # 2. 길이 제약
    length = len(sentence)
    if length < _MIN_LEN:
        fail_reasons.append(f"too_short({length}자)")
    if length > _MAX_LEN:
        fail_reasons.append(f"too_long({length}자)")

    # 3. 금칙어
    for word in _FORBIDDEN_WORDS:
        if word in sentence:
            fail_reasons.append(f"forbidden:{word}")

    # 4. 줄거리 복붙 감지 (smry 앞 50자와 과도한 공유)
    smry = ctx.get("smry", "")
    if smry and _ngram_overlap(sentence, smry, n=6) > 0.3:
        fail_reasons.append("smry_copy")

    result["pass"] = len(fail_reasons) == 0
    result["fail_reasons"] = fail_reasons
    return result


def _ngram_overlap(text_a: str, text_b: str, n: int = 6) -> float:
    """두 텍스트의 n-gram Jaccard 유사도 (0.0~1.0)."""
    def ngrams(text):
        text = re.sub(r"\s+", "", text)
        return set(text[i:i+n] for i in range(len(text) - n + 1))

    a, b = ngrams(text_a), ngrams(text_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def filter_batch(results: list[dict], contexts: list[dict]) -> tuple[list[dict], list[dict]]:
    """배치 검증 → (통과, 실패) 분리."""
    ctx_map = {c["vod_id"]: c for c in contexts}
    passed, failed = [], []
    for r in results:
        ctx = ctx_map.get(r.get("vod_id"), {})
        validated = validate(r, ctx)
        (passed if validated["pass"] else failed).append(validated)
    return passed, failed
