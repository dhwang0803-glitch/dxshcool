"""
Poster_Collection 공통 베이스 클래스.

공유 유틸리티:
  - title_similarity: 두 제목 문자열 유사도 (SequenceMatcher 기반)
"""

from difflib import SequenceMatcher


class PosterBase:
    """Poster_Collection 모듈 공통 베이스."""

    @staticmethod
    def title_similarity(a: str, b: str) -> float:
        """두 제목의 유사도 (0.0~1.0)."""
        a, b = a.lower().strip(), b.lower().strip()
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        return SequenceMatcher(None, a, b).ratio()
