"""
seasonal_matcher.py — STT/OCR 키워드 → 제철장터 실제 상품 매칭

Object_Detection에서 추출한 음식 키워드를 제철장터 편성표의
실제 상품명과 매칭하여 채널 이동/시청예약 팝업을 생성한다.

사용:
    from seasonal_matcher import SeasonalMatcher
    matcher = SeasonalMatcher("data/seasonal_market.json")
    result = matcher.match("추어탕")
    # → [{"product_name": "남원추어탕", "broadcast_date": "2026-03-24", ...}]
"""
from __future__ import annotations
import json
from pathlib import Path


class SeasonalMatcher:
    """음식 키워드 → 제철장터 상품 매칭"""

    def __init__(self, json_path: str):
        with open(json_path, encoding="utf-8") as f:
            self._products: list[dict] = json.load(f)

        # 상품명에서 키워드 추출 → 역인덱스
        # "남원추어탕" → ["추어탕", "남원"]
        # "홍성마늘등심" → ["마늘", "등심", "홍성"]
        # "아산 포기김치" → ["김치", "포기김치", "아산"]
        self._keyword_index: dict[str, list[dict]] = {}
        for product in self._products:
            name = product["product_name"]
            # 상품명 자체를 키로
            self._add_index(name, product)
            # 공백 분리
            for part in name.split():
                if len(part) >= 2:
                    self._add_index(part, product)
            # 한글 부분 매칭용 (2글자 이상 서브스트링)
            clean = name.replace(" ", "")
            for i in range(len(clean)):
                for j in range(i + 2, len(clean) + 1):
                    sub = clean[i:j]
                    if len(sub) >= 2:
                        self._add_index(sub, product)

    def _add_index(self, key: str, product: dict):
        if key not in self._keyword_index:
            self._keyword_index[key] = []
        # 중복 방지
        if product not in self._keyword_index[key]:
            self._keyword_index[key].append(product)

    @property
    def product_count(self) -> int:
        return len(set(p["product_name"] for p in self._products))

    @property
    def schedule_count(self) -> int:
        return len(self._products)

    def match(self, keyword: str) -> list[dict]:
        """
        음식 키워드 → 매칭되는 제철장터 상품 반환.
        중복 제거 (상품명 기준).
        """
        if not keyword:
            return []

        matches = self._keyword_index.get(keyword, [])
        if not matches:
            return []

        # 상품명 기준 중복 제거
        seen = set()
        unique = []
        for m in matches:
            name = m["product_name"]
            if name not in seen:
                seen.add(name)
                unique.append(self._enrich(m, keyword))
        return unique

    def match_keywords(self, keywords: list[str]) -> list[dict]:
        """여러 키워드 매칭 → 중복 제거"""
        seen = set()
        results = []
        for kw in keywords:
            for m in self.match(kw):
                if m["product_name"] not in seen:
                    seen.add(m["product_name"])
                    results.append(m)
        return results

    def _enrich(self, product: dict, keyword: str) -> dict:
        name = product["product_name"]
        return {
            "product_name": name,
            "channel": product.get("channel", "제철장터"),
            "broadcast_date": product.get("broadcast_date", ""),
            "start_time": product.get("start_time", ""),
            "end_time": product.get("end_time", ""),
            "matched_keyword": keyword,
            "ad_action_type": "seasonal_market",
            "popup_title": "🛒 제철장터 상품 안내",
            "popup_body": f"{name}\n📺 제철장터 채널 | {product.get('start_time', '')}~{product.get('end_time', '')}",
        }
