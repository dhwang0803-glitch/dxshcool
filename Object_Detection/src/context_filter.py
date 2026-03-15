"""
context_filter.py — 광고 트리거 적합성 판단

YOLO 탐지 라벨 + CLIP 점수를 교차 검증하여
오탐(금붕어 수조, 장식 과일 등)을 차단한다.

필터 구조:
  1. Global Brand Safety — 모든 ad_category 공통 차단 (재난/애니메이션)
  2. 음식 카테고리 전용 negative — 낚시·바닷속·장식 등
  3. YOLO 식기류 체크 — 음식 탐지 시 식기류 동반 필수
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

# top-1이 아니어도 이 점수 이상이면 negative 차단 (secondary check)
NEGATIVE_SECONDARY_CUTOFF = 0.22

# ── 전역 차단 (Brand Safety) — 모든 ad_category에 적용 ──────────────────
# 한국어 쿼리 기준 + 영어 호환(테스트용)
GLOBAL_NEGATIVE_KEYWORDS = {
    # 가상 콘텐츠
    "만화", "애니메이션",
    "cartoon", "anime", "animation",
    # 재난/사고
    "재난", "화재", "긴급 뉴스",
    "disaster", "accident", "funeral",
}

# ── 음식/수산물 카테고리 전용 차단 ──────────────────────────────────────
# 한국어 쿼리 기준 + 영어 호환(테스트용)
FOOD_NEGATIVE_KEYWORDS = {
    # 관상어 (수족관)
    "금붕어", "수조", "어항",
    "aquarium", "pet tank",
    # 낚시 / 자연 다큐
    "낚시", "낚싯대", "바닷속", "다이버",
    "fishing", "underwater", "diver", "marine life",
    # 장식 / 가짜 음식
    "장식용", "삽화",
    "decorative", "illustration", "painting",
}


class ContextFilter:
    """
    validate(yolo_labels, clip_scores, ad_category)
        → {"context_valid": bool, "context_reason": str}
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
            clip_scores:  {쿼리: 점수} dict (negative 쿼리 포함 전체)
            ad_category:  yaml 카테고리 키

        Returns:
            {"context_valid": bool, "context_reason": str}
        """
        # 최고 점수 쿼리 1회만 계산 (성능)
        top_query = max(clip_scores, key=clip_scores.get) if clip_scores else ""
        top_lower = top_query.lower()

        # ── 1. Global Brand Safety (모든 카테고리 공통) ──────────────────
        # top-1 체크
        for kw in GLOBAL_NEGATIVE_KEYWORDS:
            if kw in top_lower:
                return {"context_valid": False, "context_reason": f"brand_safety:{top_query}"}
        # secondary: top-1이 아니어도 cutoff 이상이면 차단
        for q, score in clip_scores.items():
            if score >= NEGATIVE_SECONDARY_CUTOFF and any(kw in q.lower() for kw in GLOBAL_NEGATIVE_KEYWORDS):
                return {"context_valid": False, "context_reason": f"brand_safety_secondary:{q}"}

        # ── 2. 음식 외 카테고리 → 이하 필터 미적용 ───────────────────────
        if ad_category not in FOOD_AD_CATEGORIES:
            return {"context_valid": True, "context_reason": "non_food_category"}

        # ── 3. 음식 카테고리 전용 negative 차단 ─────────────────────────
        # top-1 체크
        for kw in FOOD_NEGATIVE_KEYWORDS:
            if kw in top_lower:
                return {"context_valid": False, "context_reason": f"context_blocked:{top_query}"}
        # secondary: top-1이 아니어도 cutoff 이상이면 차단
        for q, score in clip_scores.items():
            if score >= NEGATIVE_SECONDARY_CUTOFF and any(kw in q.lower() for kw in FOOD_NEGATIVE_KEYWORDS):
                return {"context_valid": False, "context_reason": f"food_context_secondary:{q}"}

        # ── 4. YOLO 식기류 체크 ──────────────────────────────────────────
        has_food     = bool(FOOD_LABELS & yolo_labels)
        has_tableware = bool(TABLEWARE_LABELS & yolo_labels)

        if has_food and not has_tableware:
            return {"context_valid": False, "context_reason": "no_tableware_with_food"}

        return {"context_valid": True, "context_reason": "eating_scene"}
