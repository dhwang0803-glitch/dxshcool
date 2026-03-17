"""홈쇼핑 상품명 정규화 모듈."""

from __future__ import annotations

import re

# 1. 대괄호/소괄호 + 내용 제거
_RE_BRACKETS = re.compile(r"[\[《<〈【\(][^)\]》>〉】]*[\]》>〉】\)]")

# 2. 이모지 및 특수문자 제거
_RE_SPECIAL = re.compile(r"[●○◆◇★☆♥♡♣♠♦✔✓✿❤🩵💛💚💙💜🤍🖤🔥💥✨⭐🎁🎉🏆👍→←↑↓▶◀▷◁※&+#@!~`^|\\]")

# 3. 수량/단위 패턴 제거
_RE_QUANTITY = re.compile(
    r"\d+(?:\.\d+)?\s*(?:박스|g|kg|ml|L|리터|포|팩|종|개월|세트|매|입|봉|캡슐|정|병|EA|ea|개|회분|일분|통|쌍|켤레|장|롤|미터|cm|mm|m)\b",
    re.IGNORECASE,
)

# 4. 프로모션 키워드 제거
_PROMO_KEYWORDS = [
    "방송최저가", "가격인하", "특상품", "방송에서만", "무료배송",
    "긴급편성", "최다구성", "한정수량", "오늘만", "타임특가",
    "특별할인", "추가할인", "초특가", "역대최저", "파격가",
    "베스트셀러", "히트상품", "단독구성", "리미티드",
    "선착순", "즉시할인", "카드할인", "무이자", "사은품",
    "증정", "덤증정", "추가증정", "1+1", "2+1",
]
_RE_PROMO = re.compile("|".join(re.escape(k) for k in _PROMO_KEYWORDS))

# 5. 인명/소유격 패턴 제거 (인명+직함 또는 인명+의+공백)
_RE_POSSESSIVE = re.compile(r"[가-힣]{2,4}(?:박사|선생|셰프|원장|교수)\s*|[가-힣]{2,3}의\s(?=[가-힣])")

# 6. 앞쪽 브랜드명 제거 시도 (영문 대문자 혹은 한글 2글자 + 공백)
_RE_BRAND_PREFIX = re.compile(r"^(?:[A-Z][A-Za-z0-9]*|[가-힣]{2})\s+")

# 7. 연속 공백 정리
_RE_MULTI_SPACE = re.compile(r"\s{2,}")


def normalize(raw_name: str) -> str:
    """원본 상품명 → 정규화 상품명."""
    if not raw_name or not raw_name.strip():
        return ""

    text = raw_name

    # 1. 괄호 내용 제거
    text = _RE_BRACKETS.sub(" ", text)

    # 2. 이모지/특수문자 제거
    text = _RE_SPECIAL.sub(" ", text)

    # 3. 수량 패턴 제거
    text = _RE_QUANTITY.sub(" ", text)

    # 4. 프로모션 키워드 제거
    text = _RE_PROMO.sub(" ", text)

    # 5. 인명/소유격 제거
    text = _RE_POSSESSIVE.sub(" ", text)

    # 6. 브랜드 접두어 제거
    text = _RE_BRAND_PREFIX.sub("", text)

    # 7. 정리
    text = _RE_MULTI_SPACE.sub(" ", text).strip()

    return text
