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
    # 직접 시청 유도 (~세요/~봐요 계열 전면)
    "지금 바로", "놓치지 마세요", "한 번만",
    "보세요", "해보세요", "느껴보세요", "빠져보세요", "만나보세요",
    "경험하세요", "시청하세요", "확인하세요", "간직하세요", "즐겨보세요",
    "들어가볼까요", "함께해요", "기울여보세요", "선사하세요", "목격하세요",
    "경험해봐", "해봐", "들어봐",
    # 줄거리 요약 직접 언급
    "줄거리", "내용은",
]

_MIN_LEN = 20
_MAX_LEN = 80


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

    # 3b. "~보세요" / "~봐요" / "~봐" 계열 정규식 (공백 포함 변형 전부 차단)
    if re.search(r"[가-힣]\s*보세요|[가-힣]\s*봐요|[가-힣]\s*봐\b", sentence):
        fail_reasons.append("imperative_ending")

    # 3c. 합쇼체(설명문 어미) 금지 — 카피라이팅 톤 유지
    # [가-힣]니다: 있습니다/합니다/됩니다/사로잡니다/답니다 등 모든 ~니다 어미
    if re.search(r"[가-힣]니다", sentence):
        fail_reasons.append("formal_ending")

    # 3d. HTML 태그 금지
    if re.search(r"<[^>]+>", sentence):
        fail_reasons.append("html_tag")

    # 4. 줄거리 복붙 감지 (smry와 과도한 n-gram 중복)
    smry = ctx.get("smry", "")
    if smry and _ngram_overlap(sentence, smry, n=6) > 0.3:
        fail_reasons.append("smry_copy")

    # 5. 제목 반복 감지 (작품명 3자 이상인 경우 문구 안에 포함 여부)
    asset_nm = ctx.get("asset_nm", "")
    # 회차 번호 제거한 순수 제목 추출 (예: "트리거 02회" → "트리거")
    pure_title = re.sub(r"\s*\d+회$", "", asset_nm).strip()
    if len(pure_title) >= 3 and pure_title in sentence:
        fail_reasons.append(f"title_repeat:{pure_title}")

    # 6. 영문 감독명 포함 여부 (영문 2단어 이상 연속)
    if re.search(r"[A-Z][a-z]+ [A-Z][a-z]+", sentence):
        fail_reasons.append("english_name")

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
