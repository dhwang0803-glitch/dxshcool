"""
context_filter.py — 광고 트리거 적합성 판단

YOLO 탐지 라벨 + CLIP 점수를 교차 검증하여
오탐(금붕어 수조, 장식 과일 등)을 차단한다.

음식/식재료 카테고리만 필터 적용.
홈쇼핑·여행지 등 비음식 카테고리는 필터 미적용.
"""
from __future__ import annotations

# 음식류 탐지 시 식기류가 함께 있어야 광고 트리거
FOOD_AD_CATEGORIES = {"지방특산물", "한식", "과일채소"}

# YOLO 식기류 라벨 (COCO 80종)
TABLEWARE_LABELS = {"fork", "knife", "spoon", "bowl", "cup", "dining table", "chopsticks"}

# YOLO 음식 관련 라벨
FOOD_LABELS = {
    "fish", "apple", "banana", "orange", "broccoli", "carrot",
    "hot dog", "pizza", "donut", "cake", "sandwich",
}

# negative CLIP 쿼리 키워드 — 이 단어가 최고점 쿼리에 포함되면 차단
NEGATIVE_KEYWORDS = {"aquarium", "pet tank", "decorative", "illustration", "painting"}


class ContextFilter:
    """
    validate(yolo_labels, clip_scores, ad_category) → {"context_valid": bool, "context_reason": str}
    """

    def validate(
        self,
        yolo_labels: set[str],
        clip_scores: dict[str, float],
        ad_category: str,
    ) -> dict:
        """
        Args:
            yolo_labels:  해당 프레임의 YOLO 탐지 라벨 집합
            clip_scores:  {쿼리: 점수} dict
            ad_category:  yaml 카테고리 키 (예: "지방특산물", "홈쇼핑", "여행지")

        Returns:
            {"context_valid": bool, "context_reason": str}
        """
        # 음식 외 카테고리는 필터 미적용
        if ad_category not in FOOD_AD_CATEGORIES:
            return {"context_valid": True, "context_reason": "non_food_category"}

        # negative 쿼리가 최고 점수인 경우 차단
        if clip_scores:
            top_query = max(clip_scores, key=clip_scores.get)
            for kw in NEGATIVE_KEYWORDS:
                if kw in top_query.lower():
                    return {"context_valid": False, "context_reason": f"aquarium_filtered:{top_query}"}

        # 식기류 없이 음식만 탐지된 경우 차단
        has_food = bool(FOOD_LABELS & yolo_labels)
        has_tableware = bool(TABLEWARE_LABELS & yolo_labels)

        if has_food and not has_tableware:
            return {"context_valid": False, "context_reason": "no_tableware_with_food"}

        return {"context_valid": True, "context_reason": "eating_scene"}
