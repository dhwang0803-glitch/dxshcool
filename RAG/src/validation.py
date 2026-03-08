"""
validation.py — RAG 결과 유효성 검증 및 신뢰도 점수 계산
Phase 1 구현 (PLAN_01 2.2절)
"""
import re
from typing import List

# ─────────────────────────────────────────
# 허용 등급 집합
# ─────────────────────────────────────────

VALID_RATINGS = {
    # 한국
    '전체관람가', '12세이상관람가', '15세이상관람가', '18세이상관람가', '청소년관람불가',
    # 미국
    'G', 'PG', 'PG-13', 'R', 'NC-17',
}

# 소스별 기본 신뢰도
_SOURCE_BASE = {
    'IMDB':      0.92,
    'WIKIPEDIA': 0.80,
    'KMRB':      0.97,
    'FALLBACK':  0.60,
}

# 컬럼별 형식 패턴 (일치하면 +보너스)
_COLUMN_PATTERN = {
    'director':     re.compile(r'^[\w\s·\-]{2,30}$'),
    'cast_lead':    re.compile(r'^[\w\s·\-]{2,30}$'),
    'rating':       None,   # VALID_RATINGS 집합으로 검증
    'release_date': re.compile(r'^\d{4}-\d{2}-\d{2}$'),
}


# ─────────────────────────────────────────
# validate_director
# ─────────────────────────────────────────

def validate_director(name: str) -> bool:
    """
    감독명 유효성 검증.
    - 2~30자
    - 한국어 / 영어 / 숫자 / 공백 / 점·하이픈 허용
    """
    if not name or not name.strip():
        return False
    name = name.strip()
    if not (2 <= len(name) <= 30):
        return False
    # 한국어, 영문, 숫자, 공백, 특수(·-.) 허용
    if not re.match(r'^[\uAC00-\uD7A3a-zA-Z0-9\s·\-\.]+$', name):
        return False
    return True


# ─────────────────────────────────────────
# validate_cast
# ─────────────────────────────────────────

def validate_cast(names: List[str]) -> bool:
    """
    배우 리스트 유효성 검증.
    - 1명 이상 3명 이하
    - 각 이름은 validate_director 기준 동일
    """
    if not names or not isinstance(names, list):
        return False
    if not (1 <= len(names) <= 3):
        return False
    return all(validate_director(n) for n in names)


# ─────────────────────────────────────────
# validate_rating
# ─────────────────────────────────────────

def validate_rating(rating: str) -> bool:
    """등급 문자열이 VALID_RATINGS에 포함되는지 검증"""
    if not rating or not isinstance(rating, str):
        return False
    return rating.strip() in VALID_RATINGS


# ─────────────────────────────────────────
# validate_date
# ─────────────────────────────────────────

def validate_date(date_str: str) -> bool:
    """
    날짜 형식 검증.
    - YYYY-MM-DD 형식
    - 1900 ~ 2030 범위
    - 실제 달력 상 유효한 날짜
    """
    if not date_str or not isinstance(date_str, str):
        return False
    if not re.match(r'^\d{4}-\d{2}-\d{2}$', date_str.strip()):
        return False
    try:
        from datetime import date
        year, month, day = (int(x) for x in date_str.split('-'))
        if not (1900 <= year <= 2030):
            return False
        date(year, month, day)  # 유효하지 않은 날짜면 ValueError
        return True
    except ValueError:
        return False


# ─────────────────────────────────────────
# confidence_score
# ─────────────────────────────────────────

def confidence_score(result: str, source: str, column: str) -> float:
    """
    신뢰도 점수 계산.
    - 소스 기본 신뢰도 × 형식 일치 보너스
    - 반환: 0.0 ~ 1.0 (float)
    """
    base = _SOURCE_BASE.get(source.upper(), 0.50)

    # 형식 검증 보너스
    pattern = _COLUMN_PATTERN.get(column)
    if column == 'rating':
        format_ok = result in VALID_RATINGS if result else False
    elif pattern:
        format_ok = bool(pattern.match(result.strip())) if result else False
    else:
        format_ok = bool(result and result.strip())

    # 형식 일치 → 0.05 보너스, 불일치 → -0.10 패널티
    adjustment = 0.05 if format_ok else -0.10
    score = min(max(base + adjustment, 0.0), 1.0)
    return round(score, 3)
